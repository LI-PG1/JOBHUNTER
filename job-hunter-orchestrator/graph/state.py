"""共享状态定义：求职档案贯穿全流程"""
from typing import TypedDict, List, Dict, Any

class JobHunterState(TypedDict, total=False):
    # 用户输入
    user_goal: str                       # 原始诉求
    profile: Dict[str, Any]              # 结构化画像
    target_jobs: List[Dict[str, Any]]    # 目标岗位清单

    # 简历环节
    resume: Dict[str, Any]               # 当前简历
    resume_round: int                    # 简历迭代轮次
    resume_feedback: List[Dict[str, Any]]  # 改进建议（来自差距分析/人工）

    # 匹配环节
    match_results: List[Dict[str, Any]]  # 匹配结果（score+reasons）
    match_round: int                     # 匹配轮次
    gate_verdict: str                    # pass / fail / accept_with_issues
    gap_summary: str                     # 差距摘要

    # 面试准备环节
    interview_materials: Dict[str, Any]  # 生成的材料

    # 跟踪环节
    tracking_records: List[Dict[str, Any]]

    # 收尾
    report: Dict[str, Any]

    # 控制
    errors: List[str]
    user_approvals: Dict[str, Any]
    config: Dict[str, Any]
