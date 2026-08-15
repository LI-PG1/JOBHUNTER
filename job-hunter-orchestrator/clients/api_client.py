"""四个项目 API 客户端（骨架版：mock 实现；接入真实服务时实现各函数）"""
import os
import httpx
from typing import Any, Dict, List

RUN_MODE = os.getenv("RUN_MODE", "mock")

JL_URL = os.getenv("JL_AGENT_URL", "http://127.0.0.1:8000")
JS_URL = os.getenv("JS_AGENT_URL", "http://127.0.0.1:8001")
MS_URL = os.getenv("MS_AGENT_URL", "http://127.0.0.1:8900")
TRACKER_URL = os.getenv("TRACKER_URL", "http://127.0.0.1:8902")


def call_jl_generate(profile: Dict, jd: str, feedback: List[Dict] | None = None) -> Dict:
    """JL-Agent: POST /api/generate + 轮询 GET /api/task/{id}
    参考: 改造设计/JL-Agent_改造设计.md（reviewing 阶段 + review_feedback 参数）"""
    if RUN_MODE == "mock":
        return {"ok": True, "mock": True}
    raise NotImplementedError("接入 JL-Agent 真实 API 时实现")


def call_js_match(profile: Dict, resume: Dict) -> List[Dict]:
    """JS-Agent: POST /api/match + 轮询
    参考: 改造设计/JS-Agent_改造设计.md（混合判定：score+reasons+resume_tips）"""
    if RUN_MODE == "mock":
        return []
    raise NotImplementedError("接入 JS-Agent 真实 API 时实现")


def call_ms_material(resume: Dict, jd: str) -> Dict:
    """MS-Agent-Lite: POST /api/material + SSE/轮询
    参考: 改造设计/MS-Agent-Lite_改造设计.md（quality 参数 + reviewing 状态）"""
    if RUN_MODE == "mock":
        return {"ok": True, "mock": True}
    raise NotImplementedError("接入 MS-Agent-Lite 真实 API 时实现")


def call_tracker_add(records: List[Dict]) -> bool:
    """interview-tracker: 写入投递/面试记录"""
    if RUN_MODE == "mock":
        return True
    raise NotImplementedError("接入 interview-tracker 真实 API 时实现")
