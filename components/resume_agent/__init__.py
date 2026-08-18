"""resume_agent：JL-Agent LangChain 化组件（M2 试点产物）。

对外入口：build_resume_chain()（大脑 N3/N8 进程内调用，§3.5 P6 雏形）。
"""
from resume_agent.build import build_resume_chain

__all__ = ["build_resume_chain"]
