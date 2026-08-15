"""统一工具接口：四个子项目 = 大脑的工具节点"""
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ToolResult:
    """工具调用结果（统一契约）"""
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


class BaseTool:
    """工具基类：mock 模式返回模拟数据；real 模式走 HTTP（见各子类 _real 实现）"""

    name: str = "base"

    def __init__(self, mode: str = "mock"):
        self.mode = mode

    def call(self, payload: Dict[str, Any]) -> ToolResult:
        try:
            if self.mode == "mock":
                return self._mock(payload)
            return self._real(payload)
        except Exception as e:  # 工具级兜底：任何异常返回失败，不打断大脑
            return ToolResult(ok=False, error=f"[{self.name}] {e}")

    def _mock(self, payload: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def _real(self, payload: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError
