"""JS-Agent v0.2 应用入口：FastAPI + 静态前端。

启动：python -m uvicorn app.main:app --host 127.0.0.1 --port 8101
或：python 启动脚本
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.console import router as console_router
from .api.match import router as match_router
from .config import config
from .core.errors import JSAgentError

app = FastAPI(title="JS-Agent 岗位匹配助手（LLM-Agent 版）", version="0.2.0")
app.include_router(match_router)
app.include_router(console_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.2.0", "constraint_mode": config.constraint_mode}


@app.on_event("startup")
async def _startup() -> None:
    """启动时探测搜索通道（自动选择，透明展示）。"""
    try:
        from .plugins.search import search_plugin
        search_plugin.refresh()
    except Exception:  # noqa: BLE001
        pass


# StaticFiles 挂载在 "/" 会捕获所有未匹配路由，必须在所有 /api 路由注册之后再挂载
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.exception_handler(JSAgentError)
async def jsagent_error_handler(_: Request, exc: JSAgentError) -> JSONResponse:
    return JSONResponse(status_code=exc.code, content={"detail": exc.message})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=config.host, port=config.port, reload=False)
