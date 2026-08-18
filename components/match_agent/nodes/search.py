"""N3 搜索执行（search_execute · P0 线性版）。

P0 说明：顺序执行 plan_queries（每轮最多 2 条、无回路），结果聚合为原始条目。
真实后端走 SearchBackendChain（tools.search_backends）；mock 模式注入 FakeBackend。
P1 接入 decide/evaluate/brake 搜索回路后，本节点改为回路内 execute_action。
"""
from __future__ import annotations

from typing import Any

from match_agent.config import DEFAULT_NUM
from match_agent.state import MatchState


def search_execute(state: MatchState) -> MatchState:
    """执行全部待执行 query（P0 线性：一次跑完种子）。

    增量更新：raw 结果并入 entries 前段暂存字段 `_raw`，随后由 scrub 接管。
    实现说明：P0 将原始结果直接挂到 state["_raw_items"]，scrub 消费。
    """
    chain = state.get("_search_chain")
    if chain is None:
        raise RuntimeError("search_execute: 缺少 _search_chain（build_match_chain 注入）")

    queries = state.get("plan_queries") or []
    executed = list(state.get("executed") or [])
    raw_items: list[dict[str, Any]] = []

    for q in queries:
        if q.get("q") in executed:
            continue
        executed.append(q["q"])
        resp = chain.search(q["q"], num=DEFAULT_NUM, channel=q.get("channel"))
        # 兼容 SearchResponse（组合器）与 list[SearchResult]（单后端）
        results = resp.results if hasattr(resp, "results") else resp
        for r in results:
            raw_items.append({
                "title": r.title, "url": r.url, "snippet": r.snippet,
                "date": r.date, "query": q.get("q"),
                "backend": getattr(resp, "backend", "injected"),
            })
    history = list(state.get("history") or [])
    history.append({
        "round": state.get("rounds", 0) + 1,
        "queries": [q["q"] for q in queries],
        "raw_count": len(raw_items),
    })
    return {**state, "executed": executed, "_raw_items": raw_items, "history": history}
