"""match_agent 搜索回路刹车检查（brake_check 节点）。

设计依据：《JS搜索回路详细设计.md §3.4》五闸门（G1-G5），全确定性代码，保证回路必有终点：

- G1 轮数上限：`rounds >= max_search_rounds`
- G2 连续无新增：`no_new_rounds >= 2` 且 `rounds >= min_search_rounds`
- G3 预算上限：`budget_left <= 0`
- G4 query 去重：无待执行 query（全部已执行）
- G5 LLM 决策器连续降级：`degraded_decide >= 3`

多闸门同时满足时按 G1→G5 顺序返回首个命中（先执行的闸门优先）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BrakeResult:
    """刹车判定结果。"""
    should_converge: bool
    reason: str


def brake_check(
    *,
    rounds: int,
    max_rounds: int,
    min_rounds: int,
    no_new_rounds: int,
    budget_left: int,
    executed: set[str],
    queries: list[str],
    degraded_decide: int,
) -> BrakeResult:
    """五闸门检查。任一命中即收敛（continue 之外的唯一出口）。"""
    # G1 轮数上限
    if rounds >= max_rounds:
        return BrakeResult(True, f"G1 轮数上限: rounds={rounds}≥{max_rounds}")
    # G2 连续无新增
    if no_new_rounds >= 2 and rounds >= min_rounds:
        return BrakeResult(True, f"G2 连续无新增: 连续 {no_new_rounds} 轮无新增且 rounds={rounds}≥{min_rounds}")
    # G3 预算上限
    if budget_left <= 0:
        return BrakeResult(True, f"G3 预算耗尽: budget_left={budget_left}")
    # G4 query 去重（无待执行 query）
    if not any(q not in executed for q in queries):
        return BrakeResult(True, "G4 无待执行 query")
    # G5 LLM 决策器连续降级
    if degraded_decide >= 3:
        return BrakeResult(True, f"G5 LLM 决策器连续降级 {degraded_decide} 次")
    return BrakeResult(False, "")
