"""共享状态定义：求职档案贯穿全流程"""
from typing import TypedDict, List, Dict, Any

class JobHunterState(TypedDict, total=False):
    # 用户输入
    user_goal: str                       # 原始诉求
    profile: Dict[str, Any]              # 结构化画像
    profile_ask_round: int               # 画像追问轮数（N2 人工补充）
    missing_fields: List[str]            # 画像缺失字段（N2 检查输出）
    target_jobs: List[Dict[str, Any]]    # 目标岗位清单
    user_input: Dict[str, Any]           # 各阶段用户补充输入（如 N10 跟踪记录）

    # 简历环节
    resume: Dict[str, Any]               # 当前简历
    resume_round: int                    # 简历迭代轮次
    resume_feedback: List[Dict[str, Any]]  # 改进建议（来自差距分析/人工）
    review_results: Dict[str, Any]       # 简历审核结果（resume_agent 组件：block → verdict/rounds/rewritten/blockerCount）

    # 匹配环节
    match_results: List[Dict[str, Any]]  # 匹配结果（score+reasons）
    match_round: int                     # 匹配轮次
    gate_verdict: str                    # pass / fail / accept_with_issues
    gap_summary: str                     # 差距摘要

    # 投递清单环节（Q10）
    submission_input: Dict[str, Any]     # 四项输入：city / max_results / company_types（profile 在 state）
    submission_plan: Dict[str, Any]      # 投递清单（N9 前置生成，interrupt 展示，只推荐不引导）

    # 面试准备环节
    interview_materials: Dict[str, Any]  # 生成的材料

    # 跟踪环节
    tracking_records: List[Dict[str, Any]]

    # 收尾
    report: Dict[str, Any]

    # 控制
    errors: List[str]
    user_approvals: Dict[str, Any]
    resume_decision: Dict[str, Any]      # N9 用户定稿决定（approve/modify/reject）
    config: Dict[str, Any]
