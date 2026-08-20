"""prep_agent 执行链（生成 + 质量回路循环 · 移植 MS pipeline.js M3）。

阶段：prepare（上下文装配）→ generate（逐文件生成）→ quality（D1~D5 质量回路，on 模式自动回炉）。
进程内内存态：无 storage/持久化（与大脑集成形态一致，Q9 同款）。
"""
from __future__ import annotations

import asyncio
from typing import Any

from prep_agent.llm import LLMClient
from prep_agent.prompts import FILES, SYSTEM_GEN, build_generate_prompt
from prep_agent.quality_check import run_rule_check
from prep_agent.quality_config import get_quality_config, merge_quality_cfg
from prep_agent.reviewer import build_feedback_prompt, review_files
from prep_agent.state import PrepState


def _resume_to_text(resume: dict[str, Any] | None) -> str:
    """简历结构化 → 文本（生成上下文）。v1：拼接常见字段。"""
    r = resume or {}
    lines: list[str] = []
    identity = r.get("identity") or r.get("base") or {}
    if isinstance(identity, dict):
        if identity.get("name"):
            lines.append(f"姓名：{identity['name']}")
        if identity.get("education"):
            lines.append(f"教育：{identity['education']}")
        if identity.get("city"):
            lines.append(f"城市：{identity['city']}")
    skills = r.get("skill") or []
    if skills:
        if isinstance(skills, list):
            lines.append("技能：" + "、".join(str(s.get("name", s)) for s in skills))
        elif isinstance(skills, dict):
            lines.append("技能：" + "、".join(str(s) for s in skills.values()))
    for key, label in (("project", "项目"), ("internship", "实习"), ("experience", "经历")):
        items = r.get(key) or []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, str):
                    lines.append(f"{label}：{it}")
                elif isinstance(it, dict):
                    name = it.get("name", "")
                    detail = it.get("detail") or it.get("content") or it.get("summary") or ""
                    lines.append(f"{label}：{name}　{detail}")
    return "\n".join(lines)


def _build_context(state: PrepState) -> str:
    resume_text = state.get("resume_text") or _resume_to_text(state.get("resume"))
    job = state.get("job") or {}
    job_name = job.get("name", job.get("title", "")) if isinstance(job, dict) else str(job or "")
    jd = state.get("jd_text") or job.get("jd") or job.get("description") or ""
    parts = [
        f"【公司】{state.get('company', '')}",
        f"【岗位】{job_name}",
    ]
    if jd:
        parts.append("【岗位JD】\n" + str(jd))
    if resume_text:
        parts.append("【用户简历】\n" + str(resume_text))
    if state.get("card"):
        parts.append("【参与边界卡（数字口径权威）】\n" + str(state.get("card")))
    return "\n\n".join(p for p in parts if p)


class PrepRunner:
    """进程内面试材料生成器（组件版：无 FastAPI/storage 依赖）。"""

    def __init__(self, client: LLMClient | None = None,
                 config: dict[str, Any] | None = None) -> None:
        self.client = client or LLMClient()
        base_cfg = get_quality_config()
        self.quality_cfg = merge_quality_cfg(base_cfg, None)

    def prepare(self, state: PrepState) -> PrepState:
        state["files"] = list(FILES)
        return state

    async def generate(self, state: PrepState) -> PrepState:
        context = _build_context(state)
        state["materials"] = []
        files = state.get("files") or []

        async def _gen(f: dict[str, Any]) -> dict[str, str]:
            content = await asyncio.to_thread(
                self.client.chat_text, SYSTEM_GEN,
                build_generate_prompt(f, context),
                max_tokens=4096, temperature=0.5)
            return {"name": f["name"], "content": content}

        # 并发生成全部文件（串行 8 份 × 1 次完整 LLM 调用是耗时主因，并发可显著缩短）
        state["materials"] = await asyncio.gather(*[_gen(f) for f in files])
        state["rounds"] = 0
        state["quality_summary"] = []
        return state

    async def _rewrite(self, state: PrepState, names: list[str],
                       feedback: str) -> None:
        """携审核意见重写指定文件（in-place 更新 materials）。"""
        context = _build_context(state)
        name_set = set(names)
        mats = state.get("materials") or []
        file_map = {f["name"]: f for f in (state.get("files") or [])}

        async def _rw(mat: dict[str, Any]) -> dict[str, Any]:
            f = file_map.get(mat.get("name"))
            if not f:
                return mat
            content = await asyncio.to_thread(
                self.client.chat_text, SYSTEM_GEN,
                build_generate_prompt(f, context, feedback),
                max_tokens=4096, temperature=0.5)
            return {**mat, "content": content}

        async def _keep(mat: dict[str, Any]) -> dict[str, Any]:
            return mat

        # 并发重写命中文件，其余原样保留（gather 保持输入顺序；全部参数须为可等待对象，
        # 未命中项包恒等 coroutine，避免 gather 对 dict 参数哈希报 unhashable）
        state["materials"] = await asyncio.gather(*[
            _rw(m) if m.get("name") in name_set else _keep(m) for m in mats])

    async def quality(self, state: PrepState) -> PrepState:
        cfg = self.quality_cfg
        state["quality_summary"] = state.get("quality_summary") or []
        if not cfg["enabled"]:
            return state
        card = state.get("card", "")
        resume_text = state.get("resume_text") or _resume_to_text(state.get("resume"))
        ver = state.get("resume_ver", "")
        review_names = cfg["review_files"]
        max_rounds = cfg["max_rounds"]
        mode = cfg["mode"]

        for round_no in range(1, max_rounds + 1):
            state["rounds"] = round_no
            check = run_rule_check(card, resume_text, ver, state.get("materials") or [],
                                   review_names)
            if check["ok"]:
                # 规则通过 → D3 LLM 审核（JD 契合）
                if mode == "on" and state.get("jd_text") and review_names:
                    rev = review_files(self.client, review_names, state.get("materials") or [],
                                       jd_text=state.get("jd_text"), card=card,
                                       resume_text=resume_text, ver=ver)
                    state["quality_summary"].append({
                        "file": ",".join(review_names), "round": round_no,
                        "verdict": rev["verdict"], "issues": rev["issues"]})
                    if rev["verdict"] == "REVISE":
                        if round_no < max_rounds:
                            await self._rewrite(state, review_names,
                                                "\n\n".join(
                                                    build_feedback_prompt(i["file"] or fn, [i])
                                                    for fn in review_names
                                                    for i in rev["issues"] if not i.get("file") or i["file"] == fn))
                            continue
                        state["errors"] = state.get("errors", []) + [
                            f"D3 审核未过（{len(rev['issues'])} 项），已达轮次上限，保留最新稿"]
                break
            # 规则有 critical
            state["quality_summary"].append({
                "file": ",".join(sorted({i.get("file", "") for i in check["critical"]})),
                "round": round_no, "verdict": "FAIL", "issues": check["critical"]})
            if mode == "warn-only":
                break
            if round_no >= max_rounds:
                state["errors"] = state.get("errors", []) + [
                    f"规则质检未过（{len(check['critical'])} 项 critical），已达轮次上限，保留最新稿"]
                break
            # 按文件分组回炉
            by_file: dict[str, list[dict[str, Any]]] = {}
            for i in check["critical"]:
                by_file.setdefault(i.get("file", ""), []).append(i)
            for fname, issues in by_file.items():
                await self._rewrite(state, [fname], build_feedback_prompt(fname, issues))
        return state


async def run_prep(state: PrepState, client: LLMClient | None = None) -> PrepState:
    """组件入口（进程内，供大脑节点直接调用）。"""
    runner = PrepRunner(client=client)
    state = runner.prepare(state)
    state = await runner.generate(state)
    state = await runner.quality(state)
    state["errors"] = state.get("errors") or []
    return state
