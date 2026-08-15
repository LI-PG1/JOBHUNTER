"""大脑节点实现（骨架版：MOCK 模式可端到端跑通）

每个节点 = 一个纯函数(state) -> dict(增量更新 state)
工具调用统一走 tools/ 封装层（mock/real 开关在 tools/base.py）
"""
from typing import Any, Dict
from graph.state import JobHunterState
from tools.jl_tool import JLTool
from tools.js_tool import JSTool
from tools.ms_tool import MSTool
from tools.tracker_tool import TrackerTool
import os

# ---------- 常量（对应设计文档 §5） ----------
MATCH_PASS_THRESHOLD = 70      # 匹配达标分数
MAX_MATCH_ROUNDS = 3           # 反馈环轮数上限
MAX_FEEDBACK_ITEMS = 5         # 差距建议条数上限

RUN_MODE = os.getenv("RUN_MODE", "mock")

# 工具实例（统一入口：大脑的"手"）
JL = JLTool(RUN_MODE)
JS = JSTool(RUN_MODE)
MS = MSTool(RUN_MODE)
TRACKER = TrackerTool(RUN_MODE)


# ---------- N1 画像解析 ----------
def parse_profile(state: JobHunterState) -> Dict[str, Any]:
    """LLM：用户一句话 → 结构化画像 + 目标岗位清单（骨架版直接返回样例）"""
    return {
        "profile": {
            "background": "硕士在读，自动驾驶方向",
            "skills": ["Python", "C++", "深度学习", "感知算法"],
            "experience": [{"name": "自动驾驶感知项目", "desc": "目标检测与轨迹预测"}],
            "preference": {"city": "不限", "direction": "决策规划", "type": "实习"},
        },
        "target_jobs": [
            {"title": "自动驾驶决策规划实习生", "company": "示例公司A", "jd": "熟悉决策规划算法，掌握C++/Python，有轨迹预测经验优先"},
            {"title": "自动驾驶算法实习生", "company": "示例公司B", "jd": "熟悉深度学习，有感知或规划项目经验"},
        ],
    }


# ---------- N2 画像完整性检查（条件节点） ----------
def check_profile(state: JobHunterState) -> Dict[str, Any]:
    """规则检查必填字段；返回 missing_fields，路由由 build.py 的条件边决定"""
    profile = state.get("profile", {})
    missing = []
    if not profile.get("skills"):
        missing.append("skills")
    if not profile.get("experience"):
        missing.append("experience")
    return {"missing_fields": missing, "user_approvals": {"profile_ok": not missing}}


# ---------- N3 简历生成 ----------
def resume_generate(state: JobHunterState) -> Dict[str, Any]:
    """工具调用：JL-Agent 生成简历（携带 resume_feedback 改进）"""
    feedback = state.get("resume_feedback", [])
    result = JL.call({
        "profile": state.get("profile", {}),
        "jd": (state.get("target_jobs") or [{}])[0].get("jd", ""),
        "resume_feedback": feedback,
    })
    if not result.ok:
        return {"errors": state.get("errors", []) + [result.error]}
    resume = result.data["resume"]
    resume["round"] = state.get("resume_round", 0) + 1
    return {"resume": resume, "resume_round": state.get("resume_round", 0) + 1}


# ---------- N4 岗位匹配 ----------
def match_jobs(state: JobHunterState) -> Dict[str, Any]:
    """工具调用：JS-Agent 匹配（混合判定，返回 score+reasons）"""
    result = JS.call({
        "profile": state.get("profile", {}),
        "resume": state.get("resume", {}),
        "target_jobs": state.get("target_jobs", []),
        "match_round": state.get("match_round", 0),
    })
    if not result.ok:
        return {"errors": state.get("errors", []) + [result.error], "match_results": []}
    return {"match_results": result.data["match_results"]}


# ---------- N5 匹配质量判定（条件节点） ----------
def gate_match(state: JobHunterState) -> Dict[str, Any]:
    """混合判定：规则层(最高分≥阈值) + LLM层(语义可信度，骨架版跳过)
    返回 gate_verdict + route，路由由 build.py 条件边决定"""
    results = state.get("match_results", [])
    top = max((r["score"] for r in results), default=0)
    rnd = state.get("match_round", 0)
    if top >= MATCH_PASS_THRESHOLD:
        verdict = "pass"
    elif rnd < MAX_MATCH_ROUNDS - 1:
        verdict = "fail"
    else:
        verdict = "accept_with_issues"
    return {
        "gate_verdict": verdict,
        "gap_summary": "" if verdict == "pass" else f"最高分 {top} < {MATCH_PASS_THRESHOLD}",
    }


# ---------- N7 差距分析 ----------
def gap_analysis(state: JobHunterState) -> Dict[str, Any]:
    """LLM：对比最高分岗位 JD 与简历 → 差距建议（骨架版：预置样例）"""
    top_job = state.get("target_jobs", [{}])[0]
    jd = top_job.get("jd", "")
    feedback = [
        {"gap": "JD 强调轨迹预测，简历缺少该关键词", "suggestion": "在项目描述中补充轨迹预测相关内容", "priority": "high"},
        {"gap": "项目量化不足", "suggestion": "补充指标（如精度提升百分比）", "priority": "mid"},
    ][: MAX_FEEDBACK_ITEMS]
    # TODO(接入): LLM 分析 + 禁区词过滤（禁止编造经历）
    return {"resume_feedback": feedback}


# ---------- N8 简历改进 ----------
def resume_improve(state: JobHunterState) -> Dict[str, Any]:
    """带建议重新生成简历（复用 N3 逻辑；骨架版直接再生成一轮）"""
    new = resume_generate(state)
    new["match_round"] = state.get("match_round", 0) + 1
    return new


# ---------- N6 面试准备 ----------
def prep_materials(state: JobHunterState) -> Dict[str, Any]:
    """工具调用：MS-Agent-Lite 生成面试材料（含审核回路结果）"""
    result = MS.call({
        "resume": state.get("resume", {}),
        "jd": (state.get("target_jobs") or [{}])[0].get("jd", ""),
    })
    if not result.ok:
        return {"errors": state.get("errors", []) + [result.error]}
    return {"interview_materials": result.data["materials"]}


# ---------- N9 简历定稿确认（人工确认点） ----------
def confirm_resume(state: JobHunterState) -> Dict[str, Any]:
    """human-in-the-loop 占位：骨架版自动确认。
    TODO(接入真实确认): 使用 langgraph interrupt() + Checkpointer，
    用户确认后 resume；用户提修改意见 → 回到 resume_improve。"""
    return {
        "user_approvals": {
            **state.get("user_approvals", {}),
            "resume_final": "auto-approved(mock)",
        }
    }


# ---------- N10 面试跟踪 ----------
def track_jobs(state: JobHunterState) -> Dict[str, Any]:
    """工具调用：interview-tracker 写入投递/面试记录"""
    records = [
        {"job": r["title"], "status": "to_apply", "plan": "本周投递"}
        for r in state.get("match_results", []) if r["score"] >= MATCH_PASS_THRESHOLD
    ]
    result = TRACKER.call({"records": records})
    if not result.ok:
        return {"errors": state.get("errors", []) + [result.error]}
    return {"tracking_records": result.data["records"]}


# ---------- N11 总报告 ----------
def final_report(state: JobHunterState) -> Dict[str, Any]:
    """LLM 汇总 + 模板组装 → Markdown + JSON（骨架版：直接拼装）"""
    results = state.get("match_results", [])
    report = {
        "resume_round": state.get("resume_round", 0),
        "match_round": state.get("match_round", 0),
        "verdict": state.get("gate_verdict", ""),
        "matched": [r for r in results if r["score"] >= MATCH_PASS_THRESHOLD],
        "materials": state.get("interview_materials", {}).get("files", []),
        "tracking": state.get("tracking_records", []),
        "errors": state.get("errors", []),
        "markdown": (
            f"# 求职报告\n"
            f"- 简历迭代: {state.get('resume_round', 0)} 轮\n"
            f"- 匹配轮次: {state.get('match_round', 0)} 轮, 判定: {state.get('gate_verdict', '')}\n"
            f"- 达标岗位: {len([r for r in results if r['score'] >= MATCH_PASS_THRESHOLD])} 个\n"
            f"- 面试材料: {len(state.get('interview_materials', {}).get('files', []))} 份\n"
        ),
    }
    return {"report": report}


# ---------- N12 降级标记 ----------
def degrade_mark(state: JobHunterState) -> Dict[str, Any]:
    """反馈环到上限：标记 accept_with_issues，继续流程"""
    return {
        "gate_verdict": "accept_with_issues",
        "errors": state.get("errors", []) + ["匹配未达标但已达轮次上限，降级继续"],
    }
