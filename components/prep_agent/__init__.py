"""prep_agent —— 面试材料生成组件（M3，LangChain 组件化）。

能力：8 件套面试材料生成 + M3 质量回路（D1 数字口径 / D2 项目不漂移 /
D4 结构完整 / D5 术语一致 + D3 LLM JD 契合审核）。
进程内调用（大脑节点 N6 直接使用），无 FastAPI/storage 依赖。
"""
from prep_agent.build import build_prep_chain
from prep_agent.chain import run_prep
from prep_agent.llm import LLMClient, LLMKeyError, resolve_llm

__all__ = ["build_prep_chain", "run_prep", "LLMClient", "LLMKeyError", "resolve_llm"]
