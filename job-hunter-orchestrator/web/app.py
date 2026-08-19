"""JobHunter 大脑统一业务前端 —— FastAPI 薄封装入口。

- 静态页挂载（web/static，原生 JS 单页）
- /api/run       全流程（进程内 build_graph().compile() 同步 + HITL interrupt 生命周期）
- /api/match     岗位匹配（直连 LLM 生成 AI 推荐岗位，OpenAI 兼容接口）
- /api/console   控制台（用户自带 API Key 管理 / CLI 工具）
- /api/ai        面试追踪智能识别（对齐 interview-tracker 契约）
- /api/resume    简历 PDF 解析
- /api/health    健康探测

启动：uvicorn web.app:app --port 2025 （orchestrator 根目录 D:/TRAE/WORKSPACE/JobHunter/job-hunter-orchestrator）
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from web.routers import ai as ai_router
from web.routers import console as console_router
from web.routers import match as match_router
from web.routers import resume as resume_router
from web.routers import run as run_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="JobHunter 求职工作台", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(run_router.router, prefix="/api", tags=["run"])
app.include_router(match_router.router, prefix="/api", tags=["match"])
app.include_router(console_router.router, prefix="/api", tags=["console"])
app.include_router(ai_router.router, prefix="/api", tags=["ai"])
app.include_router(resume_router.router, prefix="/api/resume", tags=["resume"])

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/health", tags=["health"])
def health() -> dict:
    """服务与依赖探测：运行模式、骨架图、LLM Key 配置状态（前端主界面提示用）。"""
    from graph.build import build_graph  # noqa: PLC0415  骨架图可导入性
    from web.routers.console import _read_env  # noqa: PLC0415  与控制台同一套 .env 解析

    mode = os.getenv("RUN_MODE", "mock")
    env = _read_env()
    return {
        "ok": True,
        "mode": mode,
        "key_configured": bool(env.get("LLM_API_KEY", "").strip()),
        "llm_model": env.get("LLM_MODEL", ""),
        "graph": "job_hunter (build_graph 可导入)",
    }


@app.get("/", include_in_schema=False)
def index() -> object:
    from fastapi.responses import HTMLResponse

    # 静态资源版本号：取文件 mtime，改动自动失效浏览器缓存（?v=...）
    def _v(rel: str) -> str:
        try:
            return str((STATIC_DIR / rel).stat().st_mtime_ns)
        except OSError:
            return "1"

    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{CSS_V}}", _v("css/style.css"))
    html = html.replace("{{JS_V}}", _v("js/app.js"))
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
