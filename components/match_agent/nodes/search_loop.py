"""match_agent 搜索回路（search_loop · P1 装配）。

decide（LLM/规则降级）→ 执行决策动作（rewrite_query/switch_channel/deep_dive/expand）
→ 搜索 → evaluate（LLM/规则降级）→ 收录（add/merge/discard）→ brake（五闸门）。

设计依据：《JS搜索回路详细设计.md》+ P0 各节点实现。P0 线性 search_execute 保留，
本节点将搜索段升级为回路（decide/evaluate/brake 已就绪，此处完成装配）。
"""
from __future__ import annotations

from typing import Any, Callable

from match_agent.config import (BUDGET, DEFAULT_NUM, MAX_QUERIES_PER_ROUND,
                                MAX_RESULTS, MAX_SEARCH_ROUNDS, MIN_SEARCH_ROUNDS)
from match_agent.nodes.brake import brake_check
from match_agent.nodes.decide import decide
from match_agent.nodes.evaluate import evaluate
from match_agent.state import MatchState

# 无 LLM 注入时触发 decide/evaluate 的降级路径（两者均 try/except 捕获）
def _no_llm(*_args, **_kwargs):
    raise RuntimeError("search_loop: 未注入 llm_call，走规则降级")


def _queries_from_action(decision: dict[str, Any], pending: list[str]) -> list[str]:
    """决策动作 → 待执行 query 列表（switch_channel 无新词时回退未执行 query）。"""
    action = decision.get("action")
    params = decision.get("params") or {}
    if action == "rewrite_query":
        q = str(params.get("query", "")).strip()
        return [q] if q else pending[:1]
    if action == "deep_dive":
        v = str(params.get("variant", "")).strip()
        return [v] if v else pending[:1]
    if action == "expand":
        seed = str(params.get("seed_entry", "")).strip()
        return [f"{seed} 招聘"] if seed else pending[:1]
    if action == "switch_channel":
        return pending[:MAX_QUERIES_PER_ROUND] if pending else []
    return []


def _execute_query(chain: Any, query: str, channel: str | None,
                   num: int, existing_urls: set[str]) -> list[dict[str, Any]]:
    resp = chain.search(query, num=num, channel=channel)
    results = resp.results if hasattr(resp, "results") else resp
    return [{
        "title": r.title, "url": r.url, "snippet": r.snippet, "date": r.date,
        "query": query, "channel": channel or "",
        "backend": getattr(resp, "backend", "injected"),
    } for r in results]


def search_loop(state: MatchState, *, llm_call: Callable | None = None) -> MatchState:
    """P1 搜索回路：decide→执行→evaluate→收录→brake，循环至收敛（brake 为唯一出口之一）。

    兼容 P0 契约：结束时把去重后的原始条目挂 `_raw_items`（scrub 接管）。
    """
    chain = state.get("_search_chain")
    if chain is None:
        raise RuntimeError("search_loop: 缺少 _search_chain（build_match_chain 注入）")

    call = llm_call or _no_llm
    card = state.get("card") or {}
    queries = [q.get("q", "") for q in (state.get("plan_queries") or [])]
    executed: set[str] = set(state.get("executed") or [])
    raw_items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    rounds = int(state.get("rounds") or 0)
    budget_left = BUDGET
    no_new_rounds = 0
    degraded_decide = 0
    history = list(state.get("history") or [])
    round_stats: list[dict[str, Any]] = []
    target_entries = MAX_RESULTS
    decision: dict[str, Any] = {}

    while True:
        decision, d_meta = decide(
            queries, executed, rounds=rounds, min_rounds=MIN_SEARCH_ROUNDS,
            entries_count=len(raw_items), target_entries=target_entries,
            budget_left=budget_left, card=card, round_stats=round_stats,
            llm_call=call)
        if d_meta.get("degraded"):
            degraded_decide += 1
        if decision.get("action") == "converge":
            break

        pending = [q for q in queries if q not in executed]
        action_queries = _queries_from_action(decision, pending)
        if not action_queries:
            break
        action_queries = action_queries[:MAX_QUERIES_PER_ROUND]

        round_raw: list[dict[str, Any]] = []
        for q in action_queries:
            if q in executed:
                continue
            executed.add(q)
            round_raw.extend(_execute_query(chain, q, decision.get("params", {}).get("channel"),
                                            DEFAULT_NUM, seen_urls))
        if not round_raw:
            break
        rounds += 1

        annotated, ev_meta = evaluate(round_raw, seen_urls, llm_call=call)

        added = 0
        for it in annotated:
            verdict = (it.get("_eval") or {}).get("verdict", "discard")
            url = it.get("url", "")
            if verdict == "add" and url and url not in seen_urls:
                seen_urls.add(url)
                raw_items.append(it)
                added += 1
            elif verdict == "merge" and url and url in seen_urls:
                for j, e in enumerate(raw_items):
                    if e.get("url") == url:
                        raw_items[j] = it
                        added += 1
                        break
        no_new_rounds = 0 if added else no_new_rounds + 1
        round_stats.append({"round": rounds, "queries": action_queries,
                            "raw": len(round_raw), "added": added,
                            "degraded": bool(ev_meta.get("degraded"))})
        history.append({"round": rounds, "queries": action_queries,
                        "raw_count": len(round_raw), "added": added})

        br = brake_check(
            rounds=rounds, max_rounds=MAX_SEARCH_ROUNDS, min_rounds=MIN_SEARCH_ROUNDS,
            no_new_rounds=no_new_rounds, budget_left=budget_left - rounds * 2,
            executed=executed, queries=queries, degraded_decide=degraded_decide)
        if br.should_converge:
            history.append({"converge": br.reason})
            break

    budget_left = max(0, budget_left - rounds * 2)
    return {**state, "executed": sorted(executed), "_raw_items": raw_items,
            "rounds": rounds, "history": history, "budget_left": budget_left,
            "decision": decision}
