"""JS-Agent 工具：岗位匹配（混合判定结果契约）

真实接入契约（RUN_MODE=real）：
  POST {JS_AGENT_URL}/api/match        body: {profile, resume} → task_id
  GET  {JS_AGENT_URL}/api/task/{id}    轮询 → match_results: [{job_id,title,company,score,reasons,resume_tips}]
  可选: GET /api/match/{job_id}/trace  搜索轨迹审计
参考: 改造设计/JS-Agent_改造设计.md（混合判定：score+reasons+resume_tips）
"""
from typing import Any, Dict

from tools.base import BaseTool, ToolResult


class JSTool(BaseTool):
    name = "js_match"

    def _mock(self, payload: Dict[str, Any]) -> ToolResult:
        rnd = payload.get("match_round", 0)
        # 模拟：round0→55 分(不达标)，round1→67(不达标)，round2→79(达标)
        score = 55 + rnd * 12
        jobs = payload.get("target_jobs", [])
        results = [
            {
                "job_id": f"job-{i}",
                "title": j.get("title", ""),
                "company": j.get("company", ""),
                "score": score - i * 5,
                "reasons": ["技能栈匹配", "方向契合"] if i == 0 else ["部分契合"],
                "resume_tips": [],
            }
            for i, j in enumerate(jobs)
        ]
        return ToolResult(ok=True, data={"match_results": results})

    def _real(self, payload: Dict[str, Any]) -> ToolResult:
        from clients.api_client import call_js_match
        results = call_js_match(payload.get("profile", {}), payload.get("resume", {}))
        return ToolResult(ok=True, data={"match_results": results})
