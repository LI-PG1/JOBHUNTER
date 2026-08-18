"""match_agent 共享状态：MatchState（组件独立 State，§2.4）。

P0 线性链状态流转：request → card → plan_queries → entries → judged → final_list
输出契约（§6.1）：{match_results, llm_verdicts, errors}
"""
from typing import Any, TypedDict


class MatchState(TypedDict, total=False):
    # 请求/契约层
    request: dict[str, Any]          # 原始请求（profile/resume/target_jobs/resumeVer 等）
    profile: dict[str, Any]          # 结构化画像（契约输入）
    resume: dict[str, Any]           # 简历（契约输入，含版本）
    target_jobs: list[dict[str, Any]]  # 目标岗位清单（契约输入）
    resume_ver: str                  # 本次筛选所用简历版本（Q10d）

    # 解析与规划
    card: dict[str, Any]             # 画像卡（parse 输出）
    plan_queries: list[dict[str, Any]]  # 冷启动种子 query（plan 输出）

    # 搜索与洗涤
    executed: list[str]              # 已执行 query（去重）
    entries: list[dict[str, Any]]    # 已收录条目（scrub 后，摘要化）

    # 判定与排序
    judged: list[dict[str, Any]]     # 判定后条目（status/final_score/reasons/resume_tips）
    final_list: list[dict[str, Any]] # 最终清单（rank+list 后）

    # 回路与控制（P1 搜索回路接入时使用）
    rounds: int
    budget_left: int
    history: list[dict[str, Any]]    # 每轮行动/结果记录（trace）
    decision: dict[str, Any]         # 决策器输出（P1）

    # 输出契约
    match_results: list[dict[str, Any]]
    llm_verdicts: list[dict[str, Any]]
    errors: list[str]
