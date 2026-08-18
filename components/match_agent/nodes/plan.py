"""N2 搜索规划（plan_search）。

P0 说明：原实现是 LLM（PLANNER_SYSTEM）生成 ≥3 条 query（招聘平台/官网/社区 三类来源）。
P0 无 LLM，用模板生成种子 query（方向 + 城市 + 岗位词），作为 P1 决策器的冷启动种子。
"""
from __future__ import annotations

from typing import Any

from match_agent.state import MatchState


def plan_search(state: MatchState) -> MatchState:
    """画像卡 → 冷启动种子 query 列表。

    增量更新：plan_queries / executed（空）/ rounds(0) / budget_left。
    """
    card = state.get("card") or {}
    pref = card.get("preference") or {}
    city = card.get("city") or pref.get("city") or ""
    direction = pref.get("direction") or "AI"
    target_jobs = state.get("target_jobs") or []

    queries: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(q: str, channel: str, reason: str) -> None:
        if q and q not in seen:
            seen.add(q)
            queries.append({"q": q, "channel": channel, "reason": reason})

    city_prefix = f"{city} " if city else ""
    # ① 目标岗位标题（每岗位一条）
    for j in target_jobs:
        title = (j.get("title") or "").strip()
        if title:
            add(f"{city_prefix}{title} 招聘", "招聘平台", f"目标岗位:{title}")
    # ② 方向通用
    add(f"{city_prefix}{direction} 工程师 招聘", "招聘平台", f"方向:{direction}")
    add(f"{city_prefix} 大模型 算法 岗位", "社区", "方向补充")
    # ③ 兜底
    if not queries:
        add(f"{city_prefix}{direction} 岗位", "招聘平台", "兜底")
    return {
        **state,
        "plan_queries": queries,
        "executed": [],
        "rounds": 0,
        "budget_left": 12,
        "history": [],
    }
