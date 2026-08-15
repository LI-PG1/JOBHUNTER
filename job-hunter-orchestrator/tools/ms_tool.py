"""MS-Agent-Lite 工具：面试材料生成（含审核回路结果）

真实接入契约（RUN_MODE=real）：
  POST {MS_AGENT_URL}/api/material      body: {resume, jd, quality?} → task_id
  GET  {MS_AGENT_URL}/api/task/{id}     轮询/SSE → status: ...|reviewing⇄rework|done
  响应含 qualitySummary；可选 POST /api/task/{id}/rework-file
参考: 改造设计/MS-Agent-Lite_改造设计.md
"""
from typing import Any, Dict

from tools.base import BaseTool, ToolResult


class MSTool(BaseTool):
    name = "ms_material"

    def _mock(self, payload: Dict[str, Any]) -> ToolResult:
        return ToolResult(ok=True, data={
            "materials": {
                "files": ["01_自我介绍.md", "02_项目深挖.md", "05_面经.md"],
                "quality": "pass",
            }
        })

    def _real(self, payload: Dict[str, Any]) -> ToolResult:
        from clients.api_client import call_ms_material
        data = call_ms_material(payload.get("resume", {}), payload.get("jd", ""))
        return ToolResult(ok=True, data=data)
