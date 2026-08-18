"""N9 清单生成（generate_list · P0 规则版）。

对齐原 loop.py 行 348-351 + LIST_SYSTEM：从排序池截取 top MAX_RESULTS 构造最终清单。
P0 无 LLM：直接规则截断；P1 由 LIST_SYSTEM 生成 + Gate3 交叉验证（cross_check 双护栏）。
"""
from __future__ import annotations

from match_agent.config import MAX_RESULTS
from match_agent.state import MatchState


def generate_list(state: MatchState) -> MatchState:
    """ranked → final_list（契约项）。增量更新：final_list。"""
    resume_ver = state.get("resume_ver") or ""
    pool = state.get("ranked") or []
    final_list = []
    for j in pool[:MAX_RESULTS]:
        final_list.append({
            "job_id": j["job_id"],
            "title": j.get("title", ""),
            "company": j.get("company", ""),
            "url": j.get("url", ""),
            "score": j.get("final_score", 0.0),
            "status": j.get("status", "gap"),
            "reasons": j.get("reasons", []),
            "resume_tips": j.get("resume_tips", []),
            "missing_skills": j.get("missing_skills", []),
            "resumeVer": resume_ver,            # Q10d：岗位↔简历版本对应
        })
    return {**state, "final_list": final_list}
