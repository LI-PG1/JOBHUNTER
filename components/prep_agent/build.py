"""prep_agent 链装配（build_prep_chain · M3 交付物）。

对齐架构 §3.5：供大脑节点（N6 面试准备）进程内直接调用。
契约：
    输入 {resume, company, job, jd_text?, resume_ver?, card?, quality?, llm?}
    输出 {materials, quality_summary, errors}

用法（async）：
    chain = build_prep_chain(client=LLMClient(...))   # 缺省 client 为 mock
    out = await chain.ainvoke({...})
"""
from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from prep_agent.chain import PrepRunner, _build_context
from prep_agent.llm import LLMClient
from prep_agent.state import PrepState


def build_prep_chain(client: LLMClient | None = None) -> Runnable:
    """装配链：prepare → generate → quality（M3 质量回路）。"""
    runner = PrepRunner(client=client)

    def _entry(state: dict[str, Any]) -> PrepState:
        return {
            "resume": state.get("resume") or {},
            "resume_text": state.get("resume_text") or "",
            "company": state.get("company", ""),
            "job": state.get("job") or {},
            "jd_text": state.get("jd_text") or "",
            "resume_ver": state.get("resume_ver", ""),
            "card": state.get("card") or "",
            "quality": state.get("quality") or {},
            "llm": state.get("llm") or {},
            "files": [],
            "materials": [],
            "rounds": 0,
            "quality_summary": [],
            "errors": [],
        }

    def _exit(state: PrepState) -> dict[str, Any]:
        return {
            "materials": state.get("materials") or [],
            "quality_summary": state.get("quality_summary") or [],
            "errors": state.get("errors") or [],
        }

    chain: Runnable = (
        RunnableLambda(_entry)
        | RunnableLambda(runner.prepare)
        | RunnableLambda(runner.generate)
        | RunnableLambda(runner.quality)
        | RunnableLambda(_exit)
    )
    return chain
