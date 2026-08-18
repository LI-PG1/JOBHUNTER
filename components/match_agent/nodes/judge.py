"""N5 匹配判定（judge · P1 混合判定版）。

P1（改造设计 Q1/Q2 定稿）：规则硬约束（H1-H6：企业档/时效/非岗位/技能阈值）
+ LLM 软性维度（jd_fit/quality/growth + llm_score）→ final_score 融合 + 双护栏。
- 未注入 llm_call 时退化为 P0 纯规则版（无 LLM 环境仍可用）。
- final_score = 0.7×rule_score + 0.3×llm_score；护栏：|llm−rule|>25 → 拒绝 LLM 分用规则分。
"""
from __future__ import annotations

import datetime
from typing import Any, Callable

from match_agent.config import COMPANY_TYPES, FRESH_DAYS, MATCH_ACCEPT, MATCH_GAP
from match_agent.state import MatchState

JUDGE_SYSTEM = (
    "你是岗位匹配系统的「最终判定器」。给定候选岗位（JSON 数组），逐条评估软性维度并输出严格 JSON：\n"
    '{"items":[{"index":0,"llm_score":85,"jd_fit":"高","quality":"高","growth":"中","reason":"判定理由(≤30字)"}]}\n'
    "维度说明：\n"
    "1. llm_score（0-100）：岗位与画像整体契合度（软性综合分）；\n"
    "2. jd_fit：JD 与画像方向契合度（高/中/低）；\n"
    "3. quality：岗位质量/真实性（高/中/低）；\n"
    "4. growth：发展空间（高/中/低）；\n"
    "5. index 必须与输入数组下标一一对应，不得遗漏或新增；严禁编造输入中不存在的信息。"
)


def _skill_names(skills: Any) -> list[str]:
    """兼容 list[str] 与 list[dict]（含 name）两种技能格式。"""
    out: list[str] = []
    for s in skills or []:
        if isinstance(s, dict):
            name = str(s.get("name", "")).strip()
        else:
            name = str(s).strip()
        if name:
            out.append(name)
    return out


def _rule_score(card_skills: Any, jd_text: str) -> tuple[float, list[str], list[str]]:
    """画像技能 vs JD 文本命中率。返回 (score, matched, missing)。"""
    card_skills = _skill_names(card_skills)
    jd = jd_text.lower()
    matched = [s for s in card_skills if s and s.lower() in jd]
    missing = [s for s in card_skills if s and s.lower() not in jd]
    denom = max(len(card_skills), 1)
    score = round(100.0 * len(matched) / denom, 1) if card_skills else 0.0
    return score, matched, missing


def _fresh(entry: dict[str, Any]) -> bool:
    """时效：date 可解析为 YYYY-MM-DD 且距今 ≤ FRESH_DAYS 才新鲜；无日期不判（宽松兜底）。"""
    date = entry.get("date") or ""
    try:
        d = datetime.date.fromisoformat(date[:10])
    except ValueError:
        return True
    return (datetime.date.today() - d).days <= FRESH_DAYS


def _build_llm_batch(accepted: list[dict[str, Any]]) -> str:
    import json
    batch = [{"title": e.get("title", ""), "snippet": (e.get("snippet") or "")[:300],
              "matched_skills": e.get("matched_skills", [])} for e in accepted]
    return json.dumps(batch, ensure_ascii=False)


def _parse_llm_scores(obj: Any, count: int) -> dict[int, dict[str, Any]]:
    """校验并解析 LLM 软性判定输出。返回 {index → {llm_score, jd_fit, quality, growth}}。"""
    if not isinstance(obj, dict):
        return {}
    items = obj.get("items")
    if not isinstance(items, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for e in items:
        if not isinstance(e, dict):
            continue
        idx = e.get("index")
        score = e.get("llm_score")
        if not isinstance(idx, int) or not (0 <= idx < count):
            continue
        if not isinstance(score, (int, float)):
            continue
        out[idx] = {"llm_score": max(0.0, min(100.0, float(score))),
                    "jd_fit": str(e.get("jd_fit", "")),
                    "quality": str(e.get("quality", "")),
                    "growth": str(e.get("growth", "")),
                    "reason": str(e.get("reason", ""))}
    return out


def _llm_soft_judge(llm_call: Callable, accepted: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """LLM 软性维度判定。失败/非法 → 空（调用方用规则分兜底）。"""
    if not accepted:
        return {}
    try:
        obj, _ = llm_call(JUDGE_SYSTEM, _build_llm_batch(accepted), max_tokens=2000)
    except Exception:  # noqa: BLE001
        return {}
    return _parse_llm_scores(obj, len(accepted))


def judge(state: MatchState, *, llm_call: Callable | None = None) -> MatchState:
    """entries → judged（status/final_score/reasons/resume_tips）。

    P1 混合判定：accepted 条目经 LLM 软性维度融合 final_score；无 llm_call 时纯规则。
    增量更新：judged。
    """
    card = state.get("card") or {}
    skills = list(card.get("skills") or [])
    selected_types = (state.get("request") or {}).get("company_types") or COMPANY_TYPES

    judged: list[dict[str, Any]] = []
    for i, e in enumerate(state.get("entries") or []):
        reasons: list[str] = []
        status = "accepted"
        if not e.get("is_job"):
            status = "excluded"
            reasons.append("非岗位条目")
        elif e.get("company_type") and e["company_type"] != "未知" and e["company_type"] not in selected_types:
            status = "excluded"
            reasons.append(f"企业档不符:{e.get('company_type')}")
        elif not _fresh(e):
            status = "excluded"
            reasons.append(f"超时效(>{FRESH_DAYS}天)")

        score, matched, missing = _rule_score(skills, f"{e.get('title','')} {e.get('snippet','')}")
        if status == "accepted":
            if score >= MATCH_ACCEPT:
                reasons.append(f"匹配度 {score}%≥{MATCH_ACCEPT}")
            elif score >= MATCH_GAP:
                status = "gap"
                reasons.append(f"匹配度 {score}%（<{MATCH_ACCEPT}%），需补足技能:{missing}")
            else:
                status = "excluded"
                reasons.append(f"匹配度 {score}% 低于 {MATCH_GAP}% 阈值")

        judged.append({
            **e,
            "job_id": f"job-{i}",
            "rule_score": score,
            "matched_skills": matched,
            "missing_skills": missing,
            "status": status,
            "final_score": score if status != "excluded" else 0.0,
            "reasons": reasons,
            "resume_tips": ([f"补充技能:{missing}"] if status == "gap" else []),
        })

    # ---- P1：LLM 软性维度融合（仅对 accepted/gap 候选，护栏拒绝偏差过大）----
    if llm_call is not None:
        candidates = [j for j in judged if j["status"] != "excluded"]
        soft = _llm_soft_judge(llm_call, candidates)
        for j, soft_item in zip(candidates, [soft.get(i, {}) for i in range(len(candidates))]):
            if not soft_item:
                continue
            llm_score = soft_item["llm_score"]
            if abs(llm_score - j["rule_score"]) > 25:
                j["reasons"].append(f"LLM 分 {llm_score} 与规则分偏差>25，采用规则分")
                continue
            fused = round(0.7 * j["rule_score"] + 0.3 * llm_score, 1)
            j["final_score"] = fused
            j["llm_verdict"] = soft_item
            j["reasons"].append(f"LLM 软性判定 jd_fit={soft_item['jd_fit'] or '未知'}")
        state = {**state, "judged": judged}
    return {**state, "judged": judged}
