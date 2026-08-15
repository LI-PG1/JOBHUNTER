"""统一错误定义。"""
from __future__ import annotations


class JSAgentError(Exception):
    """JS-Agent 业务异常基类。"""

    def __init__(self, message: str, code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class RulesError(JSAgentError):
    """规则库加载/校验错误。"""


class ProfileError(JSAgentError):
    """画像解析错误（输入缺失/过短）。"""


class SearchError(JSAgentError):
    """联网搜索错误。"""


class ProviderNotConfiguredError(JSAgentError):
    """未配置可用的大模型 API Key。"""

    def __init__(self, message: str = "未配置可用的大模型 API Key，请先到控制台配置") -> None:
        super().__init__(message, code=400)


class AgentPlanError(JSAgentError):
    """搜索规划失败（重试耗尽）。"""


class AgentAbortedError(JSAgentError):
    """Agent 任务被用户取消。"""

    def __init__(self, message: str = "任务已取消") -> None:
        super().__init__(message, code=499)


class LLMError(JSAgentError):
    """LLM 调用/解析错误。"""
