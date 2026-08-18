"""resume_agent mock LLM provider（正式模块，供骨架 mock 模式进程内注入）。

按提示词特征分发固定 JSON：jd_analysis / summary / internship / projects / skill_extend；
fail_on 指定特征词 → 抛 AppError（验证模块级失败隔离 §5.6）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from app.core.errors import AppError, E_LLM  # noqa: E402


class MockLLMProvider:
    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on
        self.calls: list[str] = []

    async def chat(self, messages, *, json_mode=False, max_tokens=4096, temperature=0.7):
        joined = " ".join(str(m.get("content", "")) for m in messages)
        self.calls.append(joined[:40])
        if self.fail_on and self.fail_on in joined:
            raise AppError(E_LLM, "mock: LLM 调用失败")
        if "JD 分析器" in joined:
            return json.dumps({
                "direction": "大模型应用开发", "identity": "intern",
                "coreSkills": ["Python", "LangChain", "向量检索"],
                "jdFocus": "RAG 与大模型应用", "projectType": "应用项目",
                "metricStyle": "百分比/吞吐量", "quantity": {"projects": 2},
                "keywordCoverage": 0.8,
            }, ensure_ascii=False)
        if "自我评价撰写师" in joined:
            return json.dumps({"sentences": [
                {"text": "具备大模型应用与 RAG 系统开发经验，熟练掌握 Python 与 LangChain。",
                 "criticality": "high", "estimatedLines": 2},
                {"text": "善于将业务需求落地为可交付的工程方案。",
                 "criticality": "medium", "estimatedLines": 1},
            ]}, ensure_ascii=False)
        if "实习经历润色师" in joined:
            return json.dumps({"items": [{
                "company": "示例科技", "position": "算法实习生",
                "startMonth": "2025.06", "endMonth": "2025.09",
                "overview": "参与企业级 RAG 检索系统开发",
                "duties": [
                    {"text": "搭建向量检索链路，检索延迟降低 40%", "criticality": "high", "estimatedLines": 1},
                    {"text": "优化召回准确率至 89%", "criticality": "medium", "estimatedLines": 1},
                ],
            }]}, ensure_ascii=False)
        if "项目经历撰写师" in joined:
            return json.dumps({"projects": [{
                "name": "企业级 RAG 知识库", "role": "核心开发",
                "startMonth": "2025.01", "endMonth": "2025.04",
                "techStack": ["Python", "LangChain", "Milvus"],
                "items": [
                    {"text": "实现文档解析与向量化，构建 10 万级知识库", "criticality": "high", "estimatedLines": 1},
                    {"text": "设计混合检索重排，首条命中率提升至 85%", "criticality": "high", "estimatedLines": 1},
                    {"text": "封装检索接口并接入对话链路", "criticality": "medium", "estimatedLines": 1},
                ],
                "source": "ai-created", "aiFlag": True,
            }]}, ensure_ascii=False)
        if "技能规划导师" in joined:
            return json.dumps({"recommended": [
                {"category": "工具与框架", "name": "Milvus", "level": "熟悉"},
                {"category": "工具与框架", "name": "FastAPI", "level": "熟悉"},
                {"category": "算法与模型", "name": "Rerank 模型", "level": "熟悉"},
            ]}, ensure_ascii=False)
        raise RuntimeError(f"未知提示词特征: {joined[:80]}")
