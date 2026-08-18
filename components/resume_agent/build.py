"""resume_agent 链装配（build_resume_chain · M2/P3 交付物）。

对齐架构 §3.5 P6 形态雏形：供大脑节点（N3 简历生成 / N8 建议后重写）进程内直接调用。
契约：
    输入 {direction, resume, jobs, config?}
    输出 {resume, blocks, html, config, factsheet, review_results, errors}

用法（async）：
    chain = build_resume_chain(provider=LLMProvider(cfg))   # 缺省 provider 读 lib/config
    out = await chain.ainvoke({...})

P1+ 接入计划：search（联网检索）、P4 审核基准（source_materials）、P6 版本注册表。
"""
from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from resume_agent.chain import ResumeRunner
from resume_agent.state import ResumeState


def build_resume_chain(provider: Any | None = None) -> Runnable:
    """装配线性链：prepare → generate → review → build（P3 起含 review 子图）。"""
    runner = ResumeRunner(provider=provider)

    def _entry(state: dict[str, Any]) -> ResumeState:
        resume = state.get("resume") or {}
        return {
            "direction": state.get("direction", ""),
            "resume": resume,
            "jobs": state.get("jobs") or resume.get("jobs") or [],
            "source_materials": state.get("source_materials") or {},
            "errors": [],
        }

    def _exit(state: ResumeState) -> dict[str, Any]:
        return {
            "resume": state.get("resume") or {},
            "blocks": state.get("blocks") or {},
            "html": state.get("html") or "",
            "config": state.get("assembly_config") or {},
            "factsheet": state.get("factsheet") or {},
            "review_results": state.get("review_results") or {},   # P3 已填充
            "errors": state.get("errors") or [],
        }

    chain: Runnable = (
        RunnableLambda(_entry)
        | RunnableLambda(runner.prepare)
        | RunnableLambda(runner.generate)
        | RunnableLambda(runner.review)        # P3：规则审核 → blocker 重写 → 复审
        | RunnableLambda(runner.build)
        | RunnableLambda(_exit)
    )
    return chain
