"""大脑图装配：StateGraph + 条件边（对应设计文档 §1 总图 / §3 边语义表）"""
from langgraph.graph import StateGraph, START, END
from graph.state import JobHunterState
from graph.nodes import (
    parse_profile, check_profile, resume_generate, match_jobs, gate_match,
    build_submission_plan, gap_analysis, resume_improve, prep_materials,
    confirm_resume, track_jobs, final_report, degrade_mark, MAX_PROFILE_RETRIES,
)


def _route_profile(state: JobHunterState) -> str:
    """N2 画像完整性路由：
    缺失且未达追问上限 → 回环 N2 继续追问（interrupt 人工补充）；
    完整 → 简历生成；达上限仍缺失 → 结束（带缺失标记）。"""
    missing = state.get("missing_fields")
    ask_round = state.get("profile_ask_round", 0)
    if missing and ask_round < MAX_PROFILE_RETRIES:
        return "check_profile"
    if not missing:
        return "resume_generate"
    return "END_ASK"


def _route_gate(state: JobHunterState) -> str:
    """N5 匹配质量判定路由：
    pass → 投递清单生成；fail 且轮次未满 → 差距分析；轮次已满 → 降级标记"""
    verdict = state.get("gate_verdict", "fail")
    if verdict == "pass":
        return "build_submission_plan"
    if verdict == "accept_with_issues":
        return "degrade_mark"
    return "gap_analysis"


def _route_confirm(state: JobHunterState) -> str:
    """N9 投递确认路由：确认 → 面试准备；提修改 → 回 N8；拒绝/未知操作 → END。
    未知 action 保守走 END（节点内已将其重写为 reject，此处为防御层）。"""
    decision = state.get("resume_decision", {})
    action = decision.get("action", "approve")
    if action == "modify":
        return "resume_improve"
    if action != "approve":  # reject 或未知 action 均不继续面试准备
        return "END"
    return "prep_materials"


def build_graph() -> StateGraph:
    g = StateGraph(JobHunterState)

    # 节点
    g.add_node("parse_profile", parse_profile)
    g.add_node("check_profile", check_profile)
    g.add_node("resume_generate", resume_generate)
    g.add_node("match_jobs", match_jobs)
    g.add_node("gate_match", gate_match)
    g.add_node("build_submission_plan", build_submission_plan)  # Q10 投递清单生成
    g.add_node("gap_analysis", gap_analysis)
    g.add_node("resume_improve", resume_improve)
    g.add_node("prep_materials", prep_materials)
    g.add_node("confirm_resume", confirm_resume)
    g.add_node("track_jobs", track_jobs)
    g.add_node("final_report", final_report)
    g.add_node("degrade_mark", degrade_mark)

    # 边
    g.add_edge(START, "parse_profile")
    g.add_edge("parse_profile", "check_profile")
    g.add_conditional_edges(
        "check_profile", _route_profile,
        {"resume_generate": "resume_generate", "END_ASK": END, "check_profile": "check_profile"},
    )
    g.add_edge("resume_generate", "match_jobs")
    g.add_edge("match_jobs", "gate_match")
    g.add_conditional_edges(
        "gate_match", _route_gate,
        {
            "build_submission_plan": "build_submission_plan",
            "gap_analysis": "gap_analysis",
            "degrade_mark": "degrade_mark",
        },
    )
    # 反馈环：差距分析 → 简历改进 → 重新匹配
    g.add_edge("gap_analysis", "resume_improve")
    g.add_edge("resume_improve", "match_jobs")
    g.add_edge("degrade_mark", "build_submission_plan")  # 降级也生成清单（仅推荐不引导）

    # Q10：投递清单生成 → N9 投递确认（interrupt 展示清单）→ 面试准备（按已确认岗位）
    g.add_edge("build_submission_plan", "confirm_resume")
    g.add_conditional_edges(
        "confirm_resume", _route_confirm,
        {"prep_materials": "prep_materials", "resume_improve": "resume_improve", "END": END},
    )
    g.add_edge("prep_materials", "track_jobs")
    g.add_edge("track_jobs", "final_report")
    g.add_edge("final_report", END)

    return g
