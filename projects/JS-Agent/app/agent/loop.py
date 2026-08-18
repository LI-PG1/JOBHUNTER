"""Agent 循环编排（方案 v0.5 §1/§5/§6）：画像→规划→搜索→洗涤→判断→扩散→排序→生成→质检。

- 最低 3 轮搜索（每轮执行 2 条 query），动态加轮，收敛（达标 / 连续 2 轮无新增 / 上限 10 轮）
- 三层网关贯穿：画像锚定（Gate1）→ 采集收录（Gate2）→ 输出质检（Gate3）
- 进度回调供前端进度条
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse

from ..config import config
from ..core.errors import AgentAbortedError, JSAgentError
from ..core.gates import output_gate, profile_gate
from ..core.llm import llm
from ..plugins import scrub
from ..plugins.fetch import fetch_plugin
from ..plugins.writer import save as save_result
from ..services.judge import judge_service
from .planner import build_queries
from .prompts import LIST_SYSTEM, PROFILE_SYSTEM, REVIEW_SYSTEM
from .search_loop import run as search_loop_run

# ---------- 进度 ----------

STEP_WEIGHTS = {"profile": 5, "plan": 5, "search": 55, "scrub": 5, "judge": 5, "expand": 5, "list": 10, "review": 5, "save": 5}

# 企业类型全集（与 schema.py PROFILE_CARD_SCHEMA.company_types / 前端 chips 对齐）
ALL_COMPANY_TYPES = ["央企", "国企", "大型", "中型", "小型"]

_PROFILE_BASE = 0
_PLAN_BASE = STEP_WEIGHTS["profile"]
_SEARCH_BASE = _PLAN_BASE + STEP_WEIGHTS["plan"]
_SCRUB_BASE = _SEARCH_BASE + STEP_WEIGHTS["search"]
_JUDGE_BASE = _SCRUB_BASE + STEP_WEIGHTS["scrub"]
_EXPAND_BASE = _JUDGE_BASE + STEP_WEIGHTS["judge"]
_LIST_BASE = _EXPAND_BASE + STEP_WEIGHTS["expand"]
_REVIEW_BASE = _LIST_BASE + STEP_WEIGHTS["list"]
_SAVE_BASE = _REVIEW_BASE + STEP_WEIGHTS["review"]


def _is_grey(url: str) -> bool:
    """招聘平台主机（灰区：不自动抓取正文，避免违反站点规则）。"""
    host = (urlparse(url).netloc or "").lower()
    return any(g in host for g in scrub.GREY_HOSTS)


class Progress:
    def __init__(self, cb: Callable[[int, str], None], base: int = 0, span: int = 100) -> None:
        self._cb = cb
        self._base = base
        self._span = span

    def section(self, name: str, base: int, span: int) -> "Progress":
        return Progress(self._cb, base, span)

    def step(self, frac: float, msg: str) -> None:
        pct = int(self._base + self._span * max(0.0, min(frac, 1.0)))
        try:
            self._cb(pct, msg)
        except Exception:  # noqa: BLE001
            pass


# ---------- 任务状态 ----------

class TaskRegistry:
    """job_id → 任务状态（供 API 轮询）。done/failed 超过 TTL 惰性清理。"""

    TTL_SECONDS = 1800  # 结果保留 30 分钟

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str) -> None:
        with self._lock:
            self._data[job_id] = {"status": "running", "progress": 0, "message": "初始化",
                                  "result": None, "error": None, "created_at": time.time()}

    def update(self, job_id: str, pct: int, msg: str) -> None:
        with self._lock:
            if job_id in self._data:
                self._data[job_id]["progress"] = pct
                self._data[job_id]["message"] = msg

    def cancel(self, job_id: str) -> None:
        """用户取消：立即置为 cancelling（后台线程随后抛 AgentAbortedError 落 failed）。"""
        with self._lock:
            if job_id in self._data:
                self._data[job_id].update(status="cancelling", message="正在取消...")

    def done(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            if job_id in self._data:
                self._data[job_id].update(status="done", progress=100, message="完成", result=result)

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            if job_id in self._data:
                self._data[job_id].update(status="failed", error=error)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            now = time.time()
            expired = [
                k for k, d in self._data.items()
                if d.get("status") in ("done", "failed") and now - d.get("created_at", now) > self.TTL_SECONDS
            ]
            for k in expired:
                self._data.pop(k, None)
            d = self._data.get(job_id)
            return dict(d) if d else None


tasks = TaskRegistry()


# ---------- LLM 批量结构化（数据洗涤） ----------

STRUCTURE_SYSTEM = (
    "你是岗位数据的「结构化洗涤器」。给定候选岗位原始信息（JSON 数组），逐条提取为严格 JSON 数组，元素：\n"
    '{"title":"岗位名(只保留岗位名称本身，如「AI应用开发工程师」；去掉【】括号、地点、平台名(猎聘/智联/BOSS直聘等)、「招聘/招聘信息」等前后缀杂质)",'
    '"company":"公司名(提取真实雇主；「猎头顾问/HR/中介」等不算公司名，无法确定真实雇主则空串)",'
    '"city":"城市(未知则空串)",'
    '"salary":"薪资(无则空串)",'
    '"jd_text":"从摘要提取的岗位职责/要求原文(≤300字)",'
    '"updated_at":"YYYY-MM-DD(无则空串)",'
    '"is_job":true或false(是否为招聘岗位；百科/新闻/无关页面为false),'
    '"skill_line":"application|inference|both|none"(依据JD关键词：RAG/Agent/微调/提示工程→application；vLLM/推理/部署/量化/加速→inference；两者都涉及→both；无法判断→none),'
    '"industry":"AI平台|金融|制造|医疗|零售|教育|汽车|机器人|互联网|其他"(无法判断→其他),'
    '"degree":"本科|硕士|博士|不限|未知"(JD未提学历→未知),'
    '"experience":"应届|1-3年|3-5年|5年以上|不限|未知"(JD未提经验→未知)}\n'
    "规则：严禁编造原文中不存在的信息；jd_text 只做摘录不做扩写；输出必须是与输入等长的 JSON 数组。"
)


def _structure_batch(items: list[dict[str, str]], provider_id: str | None, model: str | None) -> list[dict[str, Any]]:
    if not items:
        return []
    user = json.dumps(items, ensure_ascii=False)
    try:
        obj, _ = llm.chat_json(STRUCTURE_SYSTEM, user, provider_id, model, max_tokens=3000)
    except JSAgentError:
        # 洗涤失败降级：字段留空，is_job 保守为 true（搜索器广收，不丢数据）
        return [{"title": i.get("title", ""), "company": "", "city": "", "salary": "",
                 "jd_text": i.get("snippet", "")[:300], "updated_at": i.get("date", ""),
                 "is_job": True, "skill_line": "", "industry": "", "degree": "", "experience": ""} for i in items]
    out: list[dict[str, Any]] = []
    for i, e in enumerate(obj if isinstance(obj, list) else []):
        if not isinstance(e, dict):
            continue
        raw = items[i] if i < len(items) else {}
        is_job = e.get("is_job")
        out.append({
            "title": str(e.get("title") or raw.get("title", "")),
            "company": str(e.get("company") or ""),
            "city": str(e.get("city") or ""),
            "salary": str(e.get("salary") or ""),
            "jd_text": str(e.get("jd_text") or raw.get("snippet", ""))[:500],
            "updated_at": str(e.get("updated_at") or raw.get("date", "")),
            "is_job": is_job if isinstance(is_job, bool) else True,
            "skill_line": str(e.get("skill_line") or ""),
            "industry": str(e.get("industry") or ""),
            "degree": str(e.get("degree") or ""),
            "experience": str(e.get("experience") or ""),
        })
    return out


def _collect_mode(judged: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    """按模式筛收录：match 用状态（accepted/gap，80% 门槛）；scout 洗涤有效（is_job）即收录，匹配分作参考。

    两种模式都尊重硬过滤（status=excluded：企业类型不符 / 超时效 / 地域不符等）
    与最终分底线（final_score < match_gap 不入清单，混合判定后两模式统一）。
    """
    gap = float(config.constraints["match_gap"])

    def _passes(e: dict[str, Any]) -> bool:
        return (e.get("final_score") if e.get("final_score") is not None
                else e.get("match_score") or 0) >= gap

    if mode == "match":
        return [e for e in judged if e.get("status") in ("accepted", "gap") and _passes(e)]
    return [e for e in judged if e.get("is_job", True) and e.get("status") != "excluded" and _passes(e)]


# ---------- 匹配执行器 ----------

class MatchRunner:
    def run(
        self,
        request: dict[str, Any],
        progress_cb: Callable[[int, str], None],
        abort_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        is_aborted = abort_event.is_set if abort_event else (lambda: False)
        p = Progress(progress_cb)
        provider_id = request.get("provider_id")
        model = request.get("model")
        # 搜索器模式（默认）：岗位洗涤有效（is_job）即收录，匹配分作参考排序；match 模式保留原 80% 收录门槛
        mode = request.get("mode") or "scout"
        frontend_types = request.get("company_types") or []
        max_results = int(request.get("max_results") or 20)
        constraints = config.constraints

        # ① 画像解析 + Gate1
        p.step(0.0, "解析画像...")
        card = self._parse_profile(request.get("profile_text", ""), provider_id, model, is_aborted)
        implicit = profile_gate.implicit_skills(card, request.get("profile_text", ""))
        profile_skills = [s["name"] for s in card.get("skills", [])]
        # 企业类型过滤集合 = 前端多选 ∪ 画像推断（去重保序），两端任一为空的意图都尊重：
        # 前端勾选是硬约束，画像文本声明（如"想进国企"）作补充，避免画像声明被忽略
        selected_types = list(dict.fromkeys([*frontend_types, *card.get("company_types", [])]))
        # 归一化：覆盖全部 5 类 = 全选 = 不限（前端默认全勾，此时不应误伤「未知」类型岗位）
        if selected_types and set(selected_types) >= set(ALL_COMPANY_TYPES):
            selected_types = []
        p.section("search", STEP_WEIGHTS["profile"] + STEP_WEIGHTS["plan"], STEP_WEIGHTS["search"]).step(0.0, "画像解析完成")

        # ② 搜索规划
        p.section("plan", STEP_WEIGHTS["profile"], STEP_WEIGHTS["plan"]).step(0.5, "规划搜索方案...")
        queries = build_queries(card, provider_id, model)
        p.section("search", STEP_WEIGHTS["profile"] + STEP_WEIGHTS["plan"], STEP_WEIGHTS["search"]).step(0.05, f"搜索方案就绪（{len(queries)} 条）")

        # ③ 搜索执行（搜索回路：LLM 决策行动 + 代码刹车，改造设计 §3）
        # search_agent=false → 停用决策器，退化为按 plan_queries 顺序执行（≈ 改造前 while 循环）
        sa_enabled = config.search_agent.get("enabled", True)
        if "search_agent" in request and request["search_agent"] is not None:
            sa_enabled = bool(request["search_agent"])
        sl = search_loop_run(card, queries, _structure_batch, {
            "max_results": max_results,
            "provider_id": provider_id,
            "model": model,
            "is_aborted": is_aborted,
            "enabled": sa_enabled,
            "progress": lambda frac, msg: p.section(
                "search", STEP_WEIGHTS["profile"] + STEP_WEIGHTS["plan"], STEP_WEIGHTS["search"]
            ).step(frac, msg),
        })
        entries = sl["entries"]
        rounds = sl["rounds"]
        used_backends = set(sl["backends"])
        search_trace = {
            "history": sl["history"], "converge_reason": sl["converge_reason"],
            "llm_calls": sl["llm_calls"], "rounds": sl["rounds"],
        }

        # ④ 洗涤（search_loop 已 normalize+dedupe，此处仅统计）
        p.section("scrub", _SCRUB_BASE, STEP_WEIGHTS["scrub"]).step(0.5, "数据洗涤（去重/去噪）...")
        searched = len(entries)

        # ⑤ 判断：混合判定（硬约束 → 规则技能分 → LLM 软性 → 合并仲裁，改造设计 §2）
        p.section("judge", _JUDGE_BASE, STEP_WEIGHTS["judge"]).step(0.2, "匹配度评估与筛选...")
        judged: list[dict[str, Any]] = []
        for e in entries:
            e = dict(e)
            e["jd_text"] = e.get("jd_text") or e.get("snippet") or e.get("title", "")
            judged.append(e)
        judge_llm = config.judge.get("llm_enabled", True)
        if "judge_llm" in request and request["judge_llm"] is not None:
            judge_llm = bool(request["judge_llm"])
        judge_service.judge_batch(judged, card, profile_skills, implicit, selected_types,
                                  provider_id, model, llm_enabled=judge_llm)
        candidates = _collect_mode(judged, mode)
        washed = len(candidates)

        # 深判：抓取正文精化 JD，重跑混合判定（两模式统一，改造设计 §2.6）
        changed: list[dict[str, Any]] = []
        for e in candidates:
            if is_aborted():
                raise AgentAbortedError("任务已取消")
            url = e.get("source_url", "")
            if not url or _is_grey(url):
                continue
            page = fetch_plugin.fetch(url)
            text = (page.get("text") or "").strip()
            if len(text) > 100:
                e["jd_text"] = text[:1500]
                changed.append(e)
        if changed:
            judge_service.judge_batch(changed, card, profile_skills, implicit, selected_types,
                                      provider_id, model, llm_enabled=judge_llm)
        accepted = _collect_mode(candidates, mode)

        # ⑥ 扩散：由 search_loop 的 deep_dive/expand 行动覆盖（改造设计 §3.2），此处不再追加搜索

        # ⑦ 排序（最终分降序 + 更新新者优先）
        accepted.sort(key=lambda e: (-(e.get("final_score") or e.get("match_score") or 0), (e.get("updated_at") or "")))
        final_entries = accepted[:max_results]

        # ⑧ 生成清单（LLM）+ Gate3 质检 + 修正循环
        p.section("list", _LIST_BASE, STEP_WEIGHTS["list"]).step(0.1, "生成匹配清单...")
        result = self._generate_list(card, final_entries, provider_id, model, is_aborted)
        p.section("review", _REVIEW_BASE, STEP_WEIGHTS["review"]).step(1.0, "质检完成")

        # ⑨ 保存
        p.section("save", _SAVE_BASE, STEP_WEIGHTS["save"]).step(0.5, "保存结果...")
        md_path = save_result(result, "md")
        html_path = save_result(result, "html")
        p.step(1.0, "完成")

        result["profile_summary"] = card.get("raw_summary", "")
        result["rounds_used"] = rounds
        result["backends"] = sorted(u for u in used_backends if u)
        result["files"] = {"md": str(md_path), "html": str(html_path)}
        result["_trace"] = search_trace
        # 调试统计：定位「搜索到但收录 0」的环节（洗涤前/洗涤后/清单生成）
        result["_debug"] = {"mode": mode, "searched": searched, "washed": washed,
                            "judged": len(judged), "accepted": len(accepted),
                            "search_llm_calls": search_trace["llm_calls"]}
        print(f"[scout] mode={mode} searched={searched} washed={washed} judged={len(judged)} accepted={len(accepted)} jobs={len(result.get('jobs') or [])}")
        return result

    # ---------- 子流程 ----------

    def _parse_profile(self, text: str, provider_id: str | None, model: str | None, is_aborted) -> dict[str, Any]:
        retry = config.constraints["profile_retry"]
        last_err = ""
        for i in range(retry + 1):
            if is_aborted():
                raise AgentAbortedError("任务已取消")
            try:
                card, _ = llm.chat_json(PROFILE_SYSTEM, f"我的情况：{text}", provider_id, model, max_tokens=3000)
                res = profile_gate.validate(card, text)
                if res["ok"]:
                    return res["card"]
                last_err = "；".join(res["errors"])
            except JSAgentError as exc:
                last_err = str(exc)
        raise JSAgentError(f"画像解析未通过网关校验（重试 {retry} 次）: {last_err}")

    def _generate_list(
        self, card: dict[str, Any], entries: list[dict[str, Any]],
        provider_id: str | None, model: str | None, is_aborted,
    ) -> dict[str, Any]:
        candidates = []
        for e in entries:
            lv = e.get("llm_verdict") or {}
            candidates.append({
                "title": e.get("title", ""), "company": e.get("company", ""),
                "city": e.get("city") or card.get("city", ""), "salary": e.get("salary", ""),
                "match_score": e.get("match_score", 0), "missing_skills": e.get("missing_skills", []),
                "source_url": e.get("source_url", ""), "updated_at": e.get("updated_at", ""),
                "rule_score": e.get("match_score", 0),
                "final_score": e.get("final_score") if e.get("final_score") is not None else e.get("match_score", 0),
                "llm_verdict": lv,
                "resume_tips": lv.get("resume_tips", []),
                "jd_text": (e.get("jd_text") or "")[:200],
                "skill_line": e.get("skill_line", ""), "industry": e.get("industry", ""),
                "degree": e.get("degree", ""), "experience": e.get("experience", ""),
            })
        user = (
            f"画像卡：\n{json.dumps({'city': card.get('city'), 'education': card.get('education'), 'skills': [s['name'] for s in card.get('skills', [])]}, ensure_ascii=False)}\n\n"
            f"候选岗位数据（含最终分 final_score，match_score 必须沿用 final_score，不得改写）：\n{json.dumps(candidates, ensure_ascii=False)}"
        )
        obj, _ = llm.chat_json(LIST_SYSTEM, user, provider_id, model, max_tokens=8000)

        qa_retry = config.constraints["qa_retry"]
        for attempt in range(qa_retry + 1):
            if is_aborted():
                raise AgentAbortedError("任务已取消")
            errors: list[str] = []
            jobs = obj.get("jobs", [])
            rule_by_key: dict[str, dict[str, float]] = {
                f"{c.get('title')}|{c.get('company')}": {"rule": c.get("rule_score"), "final": c.get("final_score")}
                for c in candidates}
            for j in jobs:
                errors += output_gate.validate_job(j)
                rule = rule_by_key.get(f"{j.get('title')}|{j.get('company')}")
                if rule is not None:
                    errors += output_gate.cross_check(j, rule["rule"], rule["final"])
            if not errors:
                return obj
            if attempt >= qa_retry:
                obj["jobs"] = [j for j in jobs if not output_gate.validate_job(j)]
                obj["_qa_note"] = f"质检未全过，仅保留 {len(obj['jobs'])} 条合格岗位"
                return obj
            feedback = "\n".join(f"- {e}" for e in errors[:20])
            user_fix = (
                f"上一版清单质检反馈：\n{feedback}\n\n"
                f"请修正后重新输出完整清单 JSON（格式不变；不删除未报错岗位；match_score 沿用输入 final_score；source_url 必须来自输入）。"
            )
            prev_jobs = jobs  # 上一版 jobs 保底：REVIEW 输出残缺时回退
            obj, _ = llm.chat_json(REVIEW_SYSTEM, user_fix, provider_id, model, max_tokens=8000)
            if not isinstance(obj, dict) or not obj.get("jobs"):
                # REVIEW 返回残缺（无 jobs / 空 jobs）→ 回退上一版，仅剔除校验不过的
                obj = {"summary": obj.get("summary", "") if isinstance(obj, dict) else "",
                       "jobs": [j for j in prev_jobs if not output_gate.validate_job(j)],
                       "_qa_note": "质检修正返回残缺，回退上一版合格岗位"}
        return obj


runner = MatchRunner()
