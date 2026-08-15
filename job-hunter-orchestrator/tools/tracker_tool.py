"""interview-tracker 工具：面试跟踪记录（纯工具，不改造）

真实接入契约（RUN_MODE=real）：
  POST {TRACKER_URL}/api/records       body: {records: [...]}
参考: agent_repos/interview-tracker-assistant_analysis.md
"""
from typing import Any, Dict

from tools.base import BaseTool, ToolResult


class TrackerTool(BaseTool):
    name = "tracker"

    def _mock(self, payload: Dict[str, Any]) -> ToolResult:
        return ToolResult(ok=True, data={"records": payload.get("records", [])})

    def _real(self, payload: Dict[str, Any]) -> ToolResult:
        from clients.api_client import call_tracker_add
        ok = call_tracker_add(payload.get("records", []))
        return ToolResult(ok=ok, data={"records": payload.get("records", [])})
