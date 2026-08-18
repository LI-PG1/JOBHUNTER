"""搜索 Agent 回路状态机（改造设计 §3）：LLM 决策行动 + 代码刹车兜底。

设计要点（对应改造设计 §3.2-3.5）：
- decide_next_action：LLM 决策器（rewrite_query / switch_channel / deep_dive / expand / converge）；
  调用失败 → 降级按 plan_queries 顺序执行（≈ 改造前行为）
- execute_action：渠道偏好（search_plugin.search(prefer=…)）→ 失败仍按原链回退（确定性代码兜底）
- evaluate_results：LLM 评估器（novelty/quality/discard_urls）；失败 → 保守值
- brake_check：五闸门（轮数上限 / 连续 2 轮无新增 / LLM 调用预算 / 达标 ≥target*2 / LLM 语义收敛）
- run()：主循环；被 loop.py ③ 搜索段调用替换原 while 循环与扩散段
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import config
from ..core.enterprise import classifier
from ..core.errors import AgentAbortedError, JSAgentError
from ..core.llm import llm
from ..plugins import scrub
from ..plugins.search import search_plugin
from .prompts import SEARCH_DECIDER_SYSTEM, SEARCH_EVALUATOR_SYSTEM

CHANNEL_TYPES = {"招聘平台", "官网", "社区"}


@dataclass
class SearchLoopState:
    """回路状态（改造设计 §3.2 SearchLoopState）。"""

    card: dict[str, Any]
    plan_queries: list[dict[str, Any]]
    executed: set[str] = field(default_factory=set)
    entries: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0
    max_rounds: int = 10
    min_rounds: int = 3
    budget_left: int = 12
    llm_calls: int = 0
    no_new_rounds: int = 0
    target: int = 20
    history: list[dict[str, Any]] = field(default_factory=list)
    backends: set[str] = field(default_factory=set)
    provider_id: str | None = None
    model: str | None = None
    is_aborted: Callable[[], bool] = field(default=lambda: False)
    decider_enabled: bool = True


def _decider_user(state: SearchLoopState) -> str:
    """决策器输入：画像 + 已有结果摘要（title/company/snippet 前 120 字）+ 历史 + 预算。"""
    card = state.card
    card_sum = {
        "city": card.get("city"), "education": card.get("education"),
        "skills": [s["name"] for s in card.get("skills", [])],
        "raw_summary": (card.get("raw_summary") or "")[:120],
    }
    entries_sum = [{
        "title": e.get("title", ""), "company": e.get("company", ""),
        "city": e.get("city", ""), "skill_line": e.get("skill_line", ""),
        "snippet": (e.get("jd_text") or "")[:120],
    } for e in state.entries[-10:]]  # 只看最近 10 条，避免 token 膨胀
    return (
        f"画像卡：\n{json.dumps(card_sum, ensure_ascii=False)}\n\n"
        f"已收录岗位（最近 {len(entries_sum)} 条）：\n{json.dumps(entries_sum, ensure_ascii=False)}\n\n"
        f"已执行 query：{sorted(state.executed)[-8:]}\n"
        f"轮次：{state.rounds}/{state.max_rounds}（最低 {state.min_rounds} 轮），LLM 调用余量：{state.budget_left - state.llm_calls}\n"
        f"目标收录：{state.target}（≥{state.target * 2} 可收敛），当前：{len(state.entries)}"
    )


def _qkey(state: SearchLoopState, qtext: str) -> str:
    """query 规范化 key：注入城市前缀，与 state.executed 存储口径一致（执行前统一加城市）。"""
    qtext = str(qtext).strip()
    city = str(state.card.get("city") or "")
    if city and city not in qtext:
        qtext = f"{city} {qtext}".strip()
    return qtext


def _fallback_action(state: SearchLoopState) -> dict[str, Any]:
    """降级行动：按规划 query 顺序执行（≈ 改造前 while 循环行为）。"""
    return {
        "action": "fallback",
        "queries": [{"q": q["q"], "channel": (q.get("sources") or ["招聘平台"])[0]}
                    for q in state.plan_queries if _qkey(state, q["q"]) not in state.executed],
        "note": "决策器停用或失败，按规划 query 顺序执行",
    }


def decide_next_action(state: SearchLoopState) -> dict[str, Any]:
    """LLM 决策器：输出下一行动。失败/预算用尽/停用 → 降级 fallback（按规划 query 顺序执行）。"""
    if state.llm_calls >= state.budget_left:
        return {"action": "converge", "queries": [], "note": "LLM 调用预算已用尽，强制收敛"}
    if not state.decider_enabled:
        return _fallback_action(state)
    try:
        obj, _ = llm.chat_json(SEARCH_DECIDER_SYSTEM, _decider_user(state),
                               state.provider_id, state.model, max_tokens=1200)
        state.llm_calls += 1
    except JSAgentError:
        return _fallback_action(state)
    action = str(obj.get("action") or "rewrite_query")
    queries = [q for q in (obj.get("queries") or []) if isinstance(q, dict) and str(q.get("q", "")).strip()]
    if action not in ("rewrite_query", "switch_channel", "deep_dive", "expand", "converge"):
        action = "rewrite_query"
    if action == "converge":
        queries = []
    return {"action": action, "queries": queries, "note": str(obj.get("note", ""))[:80]}


def execute_action(action: dict[str, Any], state: SearchLoopState,
                   structure_batch: Callable, max_queries: int = 2) -> list[dict[str, Any]]:
    """执行器：渠道偏好 + 重试 + LLM 结构化 + 去重。返回本轮新增 entry 列表。"""
    if action.get("action") == "converge":
        return []
    queries = [q for q in (action.get("queries") or []) if isinstance(q, dict)][:max_queries]
    if not queries:
        # 决策未给 query 或 fallback → 取规划未执行 query 补位
        queries = [{"q": q["q"], "channel": (q.get("sources") or ["招聘平台"])[0]}
                   for q in state.plan_queries if _qkey(state, q["q"]) not in state.executed][:max_queries]
    new_entries: list[dict[str, Any]] = []
    for q in queries:
        if state.is_aborted():
            raise AgentAbortedError("任务已取消")
        qtext = _qkey(state, q.get("q", ""))
        if not qtext:
            continue
        if qtext in state.executed:
            continue
        state.executed.add(qtext)
        channel = str(q.get("channel") or "")
        prefer = channel if channel in CHANNEL_TYPES else None
        resp = search_plugin.search(qtext, num=8, prefer=prefer)
        results = resp.get("results", [])
        retry = 0
        while not results and retry < 2 and resp.get("error"):
            retry += 1
            time.sleep(6)
            resp = search_plugin.search(qtext, num=8, prefer=prefer)
            results = resp.get("results", [])
        state.backends.add(resp.get("backend", ""))
        raw_items = [{"title": r.get("title", ""), "url": r.get("url", ""),
                      "snippet": r.get("snippet", ""), "date": r.get("date", "")} for r in results]
        structured = structure_batch(raw_items, state.provider_id, state.model)
        for i, r in enumerate(results):
            e = structured[i] if i < len(structured) else {}
            snippet = r.get("snippet", "")
            entry = {
                "source_url": scrub.clean_url(r.get("url", "")),
                "title": e.get("title") or r.get("title", ""),
                "company": e.get("company", ""),
                "city": e.get("city", ""),
                "salary": e.get("salary", ""),
                "jd_text": e.get("jd_text") or snippet,
                "updated_at": e.get("updated_at") or r.get("date", ""),
                "skill_line": e.get("skill_line", ""),
                "industry": e.get("industry", ""),
                "degree": e.get("degree", ""),
                "experience": e.get("experience", ""),
                "is_job": e.get("is_job", True),
                "enterprise_type": classifier.classify(e.get("company", ""), extra_text=(e.get("jd_text") or snippet)[:200]),
                "_query": qtext,
            }
            if entry["source_url"] and entry["source_url"].startswith("http"):
                new_entries.append(entry)
    state.history.append({
        "round": state.rounds, "action": action.get("action"),
        "queries": [q.get("q") for q in queries if isinstance(q, dict)],
        "note": action.get("note", ""), "new": len(new_entries),
    })
    return new_entries


def _evaluator_user(state: SearchLoopState, new_entries: list[dict[str, Any]]) -> str:
    entries_sum = [{"title": e.get("title", ""), "company": e.get("company", "")}
                   for e in state.entries[:10]]
    new_sum = [{"title": e.get("title", ""), "company": e.get("company", ""),
                "url": e.get("source_url", ""), "skill_line": e.get("skill_line", ""),
                "snippet": (e.get("jd_text") or "")[:100]} for e in new_entries[:10]]
    return (f"已有岗位（{len(state.entries)} 条，摘要）：\n{json.dumps(entries_sum, ensure_ascii=False)}\n\n"
            f"本轮新增搜索结果：\n{json.dumps(new_sum, ensure_ascii=False)}")


def evaluate_results(state: SearchLoopState, new_entries: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM 评估器：novelty/quality/discard_urls。失败或未启用 → 保守值。"""
    sa = config.search_agent
    if not sa.get("evaluator_enabled", True) or not new_entries:
        return {"novelty": "medium", "quality": "good", "discard_urls": [], "note": ""}
    if state.llm_calls >= state.budget_left:
        return {"novelty": "medium", "quality": "mixed", "discard_urls": [], "note": "预算用尽，保守评估"}
    try:
        obj, _ = llm.chat_json(SEARCH_EVALUATOR_SYSTEM, _evaluator_user(state, new_entries),
                               state.provider_id, state.model, max_tokens=1000)
        state.llm_calls += 1
    except JSAgentError:
        return {"novelty": "medium", "quality": "mixed", "discard_urls": [], "note": "评估器失败，保守值"}
    if not isinstance(obj, dict):
        return {"novelty": "medium", "quality": "mixed", "discard_urls": [], "note": "评估输出非法"}
    return {
        "novelty": obj.get("novelty") if obj.get("novelty") in ("high", "medium", "low") else "medium",
        "quality": obj.get("quality") if obj.get("quality") in ("good", "mixed", "poor") else "mixed",
        "discard_urls": [u for u in (obj.get("discard_urls") or []) if isinstance(u, str)],
        "note": str(obj.get("note", ""))[:80],
    }


def brake_check(state: SearchLoopState, new_count: int, evaluation: dict[str, Any]) -> str:
    """代码刹车（五闸门）：返回 continue | converge。机械闸门优先于 LLM 语义收敛。"""
    if state.rounds >= state.max_rounds:
        return "converge"
    if new_count < 2:
        state.no_new_rounds += 1
        if state.no_new_rounds >= 2 and state.rounds >= state.min_rounds:
            return "converge"
    else:
        state.no_new_rounds = 0
    if state.rounds >= state.min_rounds and len(state.entries) >= state.target * 2:
        return "converge"
    if evaluation.get("novelty") == "low" and evaluation.get("quality") != "good":
        return "converge"
    return "continue"


def run(
    card: dict[str, Any],
    plan_queries: list[dict[str, Any]],
    structure_batch: Callable,
    opts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """搜索回路主循环。opts: max_results / mode / provider_id / model / is_aborted / max_rounds / min_rounds。

    返回 {"entries", "rounds", "history", "llm_calls", "backends", "converge_reason"}。
    """
    opts = opts or {}
    sa = config.search_agent
    state = SearchLoopState(
        card=card,
        plan_queries=plan_queries,
        max_rounds=int(opts.get("max_rounds") or config.constraints["max_search_rounds"]),
        min_rounds=int(opts.get("min_rounds") or config.constraints["min_search_rounds"]),
        budget_left=int(sa.get("max_llm_calls", 12)),
        target=int(opts.get("max_results") or 20),
        provider_id=opts.get("provider_id"),
        model=opts.get("model"),
        is_aborted=opts.get("is_aborted") or (lambda: False),
        decider_enabled=bool(opts.get("enabled", True)),
    )
    maxq = int(sa.get("max_queries_per_round", 2))
    progress = opts.get("progress")
    converge_reason = ""
    while state.rounds < state.max_rounds:
        if state.is_aborted():
            raise AgentAbortedError("任务已取消")
        state.rounds += 1
        before = len(state.entries)
        action = decide_next_action(state)
        if progress:
            progress(0.05 + 0.85 * (state.rounds - 1) / max(state.max_rounds - 1, 1),
                     f"第 {state.rounds} 轮搜索：{action.get('action')} {action.get('note', '')}"[:60])
        new_entries = execute_action(action, state, structure_batch, maxq)
        state.entries.extend(new_entries)
        # LLM 决策收敛：作为提前信号结束搜索，但不得突破最低轮数闸门（改造设计 §3.5）
        if action.get("action") == "converge" and state.rounds >= state.min_rounds:
            converge_reason = f"decider_converge rounds={state.rounds}"
            break
        evaluation = evaluate_results(state, new_entries)
        discard = set(evaluation.get("discard_urls") or [])
        if discard:
            state.entries = [e for e in state.entries if e.get("source_url") not in discard]
        verdict = brake_check(state, len(new_entries) - len(discard), evaluation)
        if verdict == "converge":
            converge_reason = f"rounds={state.rounds} new={len(new_entries)} novelty={evaluation.get('novelty')}"
            break
    state.entries = scrub.dedupe(scrub.normalize(state.entries))
    return {
        "entries": state.entries,
        "rounds": state.rounds,
        "history": state.history,
        "llm_calls": state.llm_calls,
        "backends": sorted(state.backends),
        "converge_reason": converge_reason,
    }
