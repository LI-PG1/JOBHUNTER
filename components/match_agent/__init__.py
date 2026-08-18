"""match_agent：JS-Agent LangChain 化组件（M1 试点产物）。

对外入口：build_match_chain()（§6.1 契约，进程内调用 Q9）。
"""
from match_agent.build import build_match_chain

__all__ = ["build_match_chain"]
