"""大脑图装配：StateGraph + 条件边（对应设计文档 §1 总图 / §3 边语义表）"""
from langgraph.graph import StateGraph, START, END
from graph.state import JobHunterState
from graph.nodes import (
    parse_profile, check_profile, resume_generate, match_jobs, gate_match,
    gap_analysis, resume_improve, prep_materials, confirm_resume,
    track_jobs, final_report, degrade_mark,
)


def _route_profile(state: JobHunterState) -> str:
    """N2 画像完整性 → 完整则进简历生成；缺失则结束（追问由前端/后续版本实现）"""
    return "resume_generate" if not state.get("missing_fields") else "END_ASK"


def _route_gate(state: JobHunterState) -> str:
    """N5 匹配质量判定路由：
    pass → 面试准备；fail 且轮次未满 → 差距分析；轮次已满 → 降级标记"""
    verdict = state.get("gate_verdict", "fail")
    if verdict == "pass":
        return "prep_materials"
    if verdict == "accept_with_issues":
        return "degrade_mark"
    return "gap_analysis"


def build_graph() -> StateGraph:
    g = StateGraph(JobHunterState)

    # 节点
    g.add_node("parse_profile", parse_profile)
    g.add_node("check_profile", check_profile)
    g.add_node("resume_generate", resume_generate)
    g.add_node("match_jobs", match_jobs)
    g.add_node("gate_match", gate_match)
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
        {"resume_generate": "resume_generate", "END_ASK": END},
    )
    g.add_edge("resume_generate", "match_jobs")
    g.add_edge("match_jobs", "gate_match")
    g.add_conditional_edges(
        "gate_match", _route_gate,
        {
            "prep_materials": "prep_materials",
            "gap_analysis": "gap_analysis",
            "degrade_mark": "degrade_mark",
        },
    )
    # 反馈环：差距分析 → 简历改进 → 重新匹配
    g.add_edge("gap_analysis", "resume_improve")
    g.add_edge("resume_improve", "match_jobs")
    g.add_edge("degrade_mark", "prep_materials")

    g.add_edge("prep_materials", "confirm_resume")
    g.add_edge("confirm_resume", "track_jobs")
    g.add_edge("track_jobs", "final_report")
    g.add_edge("final_report", END)

    return g
