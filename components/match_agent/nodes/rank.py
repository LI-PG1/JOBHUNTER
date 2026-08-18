"""N8 排序（rank）。

对齐原 loop.py 行 344-346：accepted 按 (-final_score, updated_at) 排序。
P0 仅 final_score 降序（date 缺失排后）。judged 保持全量（含 excluded，
供 save 聚合 reject_reasons），排序结果写入独立字段 ranked。
"""
from __future__ import annotations

from match_agent.state import MatchState


def rank(state: MatchState) -> MatchState:
    """judged → ranked（排除 excluded 后的排序列表）。增量更新：ranked。"""
    pool = [j for j in state.get("judged") or [] if j.get("status") != "excluded"]
    pool.sort(key=lambda j: (-j.get("final_score", 0), j.get("date", "")))
    return {**state, "ranked": pool}
