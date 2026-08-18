"""prep_agent 术语表（D5 术语一致性 · 移植 MS glossary.js）。

仅保留含英文字母的术语键（纯中文术语无大小写问题，quality_check 跳过）。
用途：check_glossary 检测「精确大写」与「忽略大小写」计数不一致 → 大小写混用。
"""
from __future__ import annotations

# 英文术语键（来自 MS glossary.js，D5 大小写一致性检测用）
GLOSSARY_TERMS = [
    "Agent", "LLM", "ReAct", "Orchestrator", "Critic", "RAG", "Reranker",
    "Embedding", "BM25", "RRF", "Cross-Encoder", "Bi-Encoder",
    "Corrective RAG", "Self-RAG", "GraphRAG", "LLM-as-Judge",
    "Function Calling", "Tool Use", "MCP", "JSON Schema", "Prompt",
    "System Prompt", "Prompt 注入", "CoT", "MoE", "SFT", "token",
    "context window", "few-shot", "Plan-then-Execute", "Reflexion",
    "MetaGPT", "SSE", "OpenAI 兼容 API", "LoRA", "QLoRA", "PEFT",
    "bitsandbytes", "GPTQ", "AWQ", "DeepSpeed", "vLLM", "KV Cache",
    "paged attention", "GQA", "MLA", "Kubernetes", "K8s", "Docker",
    "GPU", "CUDA", "NCCL", "Python", "C++", "FastAPI", "Gradio",
    "LangChain", "LangGraph", "Milvus", "Chroma", "PyTorch",
    "Transformers", "PyTorch-TensorRT", "TensorRT-LLM", "TensorRT",
    "ONNX", "TRT", "deepspeed", "vllm", "flash-attention",
]
