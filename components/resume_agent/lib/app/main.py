"""简历生成助手后端入口：/api/health + 静态前端 + 规则加载 + P2 CRUD。"""
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import adjust as adjust_api
from .api import generate as generate_api
from .api import resume as resume_api
from .api import search as search_api
from .api import settings as settings_api
from .api import skills as skills_api
from .api import upload as upload_api
from .config import PROJECT_ROOT, load_config
from .core.errors import AppError
from .core.rules import RulesLoader
from .engine.cache import GenCache
from .search.api_search import ApiSearchClient
from .storage import Storage
from .version import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    rules = RulesLoader(cfg.paths.rules_dir)
    rules.load_all()  # 规则缺失/非法 → 启动即报错（fail fast）
    app.state.config = cfg
    app.state.rules = rules
    app.state.storage = Storage(cfg.paths.data_dir)
    # 设置控制台（§5.4）：已保存的 API Key 注入环境变量，provider 按 os.getenv 读取
    saved = app.state.storage.load_settings()
    if saved.get("apiKey"):
        os.environ[cfg.provider.api_key_env] = saved["apiKey"]
    app.state.search_client = ApiSearchClient(cfg)
    app.state.gen_cache = GenCache(cfg.paths.data_dir)
    app.state.now = lambda: datetime.now().astimezone().isoformat(timespec="seconds")
    yield


app = FastAPI(title="简历生成助手", version=__version__, lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    status = 400 if exc.code < 50000 else 500
    return JSONResponse(
        status_code=status,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )


@app.get("/api/health")
def health():
    rules = app.state.rules
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "status": "up",
            "version": __version__,
            "rules": rules.versions,
        },
    }


app.include_router(resume_api.router)
app.include_router(upload_api.router)
app.include_router(skills_api.router)
app.include_router(search_api.router)
app.include_router(generate_api.router)
app.include_router(adjust_api.router)
app.include_router(settings_api.router)


app.mount("/", StaticFiles(directory=str(PROJECT_ROOT / "frontend"), html=True), name="frontend")
