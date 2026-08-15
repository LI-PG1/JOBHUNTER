"""搜索路由（契约 §4.2）：搜索模式检测。deep_mode（BrowserSkill）默认关。"""
from fastapi import APIRouter, Request

from ..core.providers import LLMProvider

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/mode", response_model=dict)
def search_mode(request: Request):
    """搜索能力检测：{apiReady, deepAvailable, missing[]}。"""
    cfg = request.app.state.config
    client = request.app.state.search_client
    missing = []
    if not client.ready:
        missing.append(cfg.search.api_key_env)
    if not LLMProvider(cfg, request.app.state.storage).ready:
        missing.append(cfg.provider.api_key_env)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "apiReady": client.ready,
            "deepAvailable": False,  # BrowserSkill 默认关（P4+ 支持）
            "missing": missing,
        },
    }
