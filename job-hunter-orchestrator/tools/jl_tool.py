"""JL-Agent 工具：简历生成（含审核回路结果）

真实接入契约（RUN_MODE=real）：
  POST {JL_AGENT_URL}/api/generate      body: {profile, jd, resume_feedback?}
  GET  {JL_AGENT_URL}/api/task/{id}     轮询 → status: analyzing|generating|reviewing|building|done
  可选: GET /api/task/{id}/review       审核明细
参考: 改造设计/JL-Agent_改造设计.md
"""
from typing import Any, Dict

from tools.base import BaseTool, ToolResult


class JLTool(BaseTool):
    name = "jl_resume"

    def _mock(self, payload: Dict[str, Any]) -> ToolResult:
        feedback = payload.get("resume_feedback", [])
        resume = {
            "summary": "自动驾驶方向硕士，熟悉决策规划与感知算法"
                       + (f"（已按建议改进：{len(feedback)} 条）" if feedback else ""),
            "projects": [{"name": "自动驾驶感知项目", "desc": "目标检测与轨迹预测"}],
            "skills": payload.get("profile", {}).get("skills", []),
            "quality": "pass",
        }
        return ToolResult(ok=True, data={"resume": resume})

    def _real(self, payload: Dict[str, Any]) -> ToolResult:
        from clients.api_client import call_jl_generate
        call_jl_generate(payload.get("profile", {}), payload.get("jd", ""),
                         payload.get("resume_feedback"))
        return ToolResult(ok=True, data={})
