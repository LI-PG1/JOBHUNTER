"""match_agent 链装配（build_match_chain · M1/P0 交付物）。

按 §2.5 P0：9 步拆成 LangChain 线性链跑通（无回路、无 LLM 判定，行为≈现状）。
契约（§6.1）：
    输入 {profile, resume, target_jobs, resumeVer}
    输出 {match_results, llm_verdicts, errors}

用法：
    chain = build_match_chain(backend="mock")          # 离线可跑
    chain = build_match_chain(backend="real")          # 真实搜索后端
    out = chain.invoke({"profile": {...}, "resume": {...}, "target_jobs": [...], "resumeVer": "line-v1"})

P1 接入计划（注释）：搜索回路（decide/evaluate/brake 并入 search 段）+ judge 混合判定
（H1-H6 + LLM 软性维度）+ parse/plan LLM 化。链结构不变，仅节点内部升级。
"""
from __future__ import annotations

from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from match_agent.nodes.judge import judge
from match_agent.nodes.list import generate_list
from match_agent.nodes.parse import parse_profile
from match_agent.nodes.plan import plan_search
from match_agent.nodes.rank import rank
from match_agent.nodes.save import save
from match_agent.nodes.scrub import scrub
from match_agent.nodes.search_loop import search_loop
from match_agent.state import MatchState
from match_agent.tools.fake_backend import FakeSearchBackend
from match_agent.tools.search_backends import SearchBackendChain


def _entry(state: dict[str, Any]) -> dict[str, Any]:
    """契约输入 → MatchState 初始态。"""
    return {
        "request": state,
        "profile": state.get("profile") or {},
        "resume": state.get("resume") or {},
        "target_jobs": state.get("target_jobs") or [],
        "resume_ver": state.get("resumeVer") or "",
        "errors": [],
    }


def _exit(state: MatchState) -> dict[str, Any]:
    """MatchState → 契约输出（§6.1 + Q7 gap_summary）。"""
    return {
        "match_results": state.get("match_results") or [],
        "gap_summary": state.get("gap_summary") or {},
        "llm_verdicts": state.get("llm_verdicts") or [],
        "errors": state.get("errors") or [],
    }


def _search_chain(backend: str) -> Any:
    """按 backend 构造搜索链注入（P0）。real 走七后端回退链；mock 走 Fake。"""
    if backend == "real":
        return SearchBackendChain()
    return FakeSearchBackend()


def build_match_chain(backend: str = "mock", search_chain: Any | None = None,
                      llm_call: Any | None = None) -> Runnable:
    """装配链：parse → plan → search（P1 回路）→ scrub → judge（P1 混合判定）→ rank → list → save。

    Args:
        backend: "mock" | "real"（搜索后端模式；real 需网络/Key）。
        search_chain: 可选注入（测试用），缺省按 backend 构造。
        llm_call: 可选 LLM 调用（system,user,**kwargs)→(obj,meta)；不注入时
                  search 回路与 judge 自动走规则降级（无 LLM 环境仍可用）。
    """
    chain_impl = search_chain if search_chain is not None else _search_chain(backend)

    def _parse(state: MatchState) -> MatchState:
        return parse_profile(state)

    def _plan(state: MatchState) -> MatchState:
        return plan_search(state)

    def _search(state: MatchState) -> MatchState:
        return search_loop({**state, "_search_chain": chain_impl}, llm_call=llm_call)

    def _scrub(state: MatchState) -> MatchState:
        return scrub(state)

    def _judge(state: MatchState) -> MatchState:
        return judge(state, llm_call=llm_call)

    def _rank(state: MatchState) -> MatchState:
        return rank(state)

    def _list(state: MatchState) -> MatchState:
        return generate_list(state)

    def _save(state: MatchState) -> MatchState:
        return save(state)

    chain: Runnable = (
        RunnableLambda(_entry)
        | RunnableLambda(_parse)
        | RunnableLambda(_plan)
        | RunnableLambda(_search)
        | RunnableLambda(_scrub)
        | RunnableLambda(_judge)
        | RunnableLambda(_rank)
        | RunnableLambda(_list)
        | RunnableLambda(_save)
        | RunnableLambda(_exit)
    )
    return chain
