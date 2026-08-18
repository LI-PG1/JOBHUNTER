"""设置控制台（§5.4 本地配置）：多 Provider 管理 + 插件默认值。

存储于 data/settings.json（git 忽略）。结构：
{
  "apiKey": "",              # 兼容旧版：单 Key（等价于一个 DeepSeek provider）
  "deepSearchDefault": true,
  "watermarkDefault": "formal",
  "searchApiKey": "",        # 联网搜索（Tavily）Key
  "providers": [{id, name, baseUrl, model, apiKey, capabilities, enabled, order}],
  "activeProviderId": "..."
}
- 激活 provider 的 Key 写入环境变量（os.environ），无需重启即对 LLMProvider 生效。
- 自检：POST /api/settings/providers/test 用最小请求验证 Key / Base URL / 模型。
"""
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import Field

from ..config import Config, mask_key
from ..core.errors import AppError
from ..schemas import CamelModel

router = APIRouter(prefix="/api/settings", tags=["settings"])

PROVIDER_FIELDS = ("id", "name", "baseUrl", "model", "apiKey", "capabilities", "enabled", "order")

# 可集成插件注册表（外部 CLI/项目；双层启动：一键配置 + 手动勾选）
# runtime.manager/bin 用于依赖检测与自动安装；runtime.dir 表示「克隆项目目录」检测（git clone 类插件）；
# features 为功能模块（精细控制）；defaultConfig 为默认参数；loginNotice 为配置前醒目提示（如 MediaCrawler 需扫码登录）。
PLUGIN_REGISTRY = [
    {
        "id": "opencli",
        "name": "OpenCLI",
        "category": "内容获取",
        "source": "https://github.com/jackwener/OpenCLI",
        "description": "100+ 站点一键 CLI：知乎热榜/搜索、B站、小红书、X/Twitter、Reddit、微博等。复用本机 Chrome 登录态，凭证不出浏览器。",
        "runtime": {"manager": "npm", "bin": "opencli",
                    "install": ["npm", "install", "-g", "@jackwener/opencli"]},
        "features": [
            {"id": "search", "name": "内容搜索", "default": True},
            {"id": "hot", "name": "热榜获取", "default": False},
        ],
        "defaultConfig": {"format": "json", "limit": 5},
    },
    {
        "id": "mediacrawler",
        "name": "MediaCrawler",
        "category": "内容获取",
        "source": "https://github.com/NanmiCoder/MediaCrawler",
        "description": "小红书/抖音/快手/B站/微博/贴吧/知乎 7 平台采集：关键词搜索、帖子与评论、创作者主页。",
        "runtime": {"manager": "git", "dir": "plugins/MediaCrawler", "bin": "MediaCrawler",
                    "checkFile": "main.py",
                    "install": ["git", "clone", "--depth", "1",
                                "https://github.com/NanmiCoder/MediaCrawler.git", "plugins/MediaCrawler"]},
        "features": [
            {"id": "search", "name": "关键词搜索", "default": True},
            {"id": "comment", "name": "评论采集", "default": False},
            {"id": "homepage", "name": "创作者主页", "default": False},
        ],
        "defaultConfig": {"maxConcurrency": 1, "storeType": "csv"},
        "loginNotice": "需扫码登录：首次使用需用 Chrome 打开目标平台并扫码登录账号，采集时复用该登录态，请确保操作前已完成登录。",
    },
    {
        "id": "agent-reach",
        "name": "Agent-Reach",
        "category": "内容获取",
        "source": "https://github.com/Panniantong/Agent-Reach",
        "description": "16 平台能力层：网页/YouTube/RSS/GitHub/X/Reddit/小红书/抖音/微博等，零 API 费用，多后端自动切换。",
        "runtime": {"manager": "pip", "bin": "agent-reach",
                    "install": ["pip", "install", "-U", "agent-reach"]},
        "features": [
            {"id": "web", "name": "网页读取", "default": True},
            {"id": "social", "name": "社媒搜索", "default": False},
            {"id": "youtube", "name": "YouTube 字幕", "default": False},
        ],
        "defaultConfig": {"format": "json"},
    },
    {
        "id": "zhihu-cli",
        "name": "zhihu-cli",
        "category": "内容获取",
        "source": "https://github.com/dawnswwwww/zhihu-cli",
        "description": "知乎内容获取：按关键词搜索高赞回答与资料。npm 一键安装、免 Cookie（基于知乎开放平台 API）。",
        "runtime": {"manager": "npm", "bin": "zhihu-cli",
                    "install": ["npm", "install", "-g", "zhihu-cli"]},
        "features": [
            {"id": "search", "name": "关键词搜索", "default": True},
            {"id": "hot", "name": "热榜获取", "default": False},
            {"id": "article", "name": "回答/文章下载", "default": False},
        ],
        "defaultConfig": {"language": "zh", "maxResults": 10, "format": "json"},
    },
    {
        "id": "ats-checker",
        "name": "ats-checker",
        "category": "ATS 预检",
        "source": "https://github.com/pranavraut033/ats-checker",
        "description": "投递前简历 ATS 兼容性评分（0-100），零依赖 npm 工具。",
        "runtime": {"manager": "npm", "bin": "ats-checker",
                    "install": ["npm", "install", "-g", "ats-checker"]},
        "features": [
            {"id": "score", "name": "ATS 评分", "default": True},
            {"id": "report", "name": "详细报告", "default": False},
        ],
        "defaultConfig": {"format": "json"},
    },
    {
        "id": "markdown-cv",
        "name": "markdown-cv",
        "category": "模板输出",
        "source": "https://github.com/elipapa/markdown-cv",
        "description": "将简历输出为 Markdown 格式，便于网页/文档场景复用。",
        "runtime": {"manager": "git", "dir": "plugins/markdown-cv", "bin": "markdown-cv",
                    "checkFile": "index.md",
                    "install": ["git", "clone", "--depth", "1",
                                "https://github.com/elipapa/markdown-cv.git", "plugins/markdown-cv"]},
        "features": [
            {"id": "render", "name": "Markdown 渲染", "default": True},
            {"id": "pdf", "name": "PDF 导出", "default": False},
        ],
        "defaultConfig": {"format": "markdown"},
    },
]


def _plugin_or_404(plugin_id: str) -> dict:
    for p in PLUGIN_REGISTRY:
        if p["id"] == plugin_id:
            return p
    raise AppError(40001, f"插件不存在: {plugin_id}", {"pluginId": plugin_id})


def _plugins_view(s: dict) -> list[dict]:
    """插件注册表 + 双层启动状态（启用勾选 + 一键配置结果）。"""
    enabled = s.get("pluginsEnabled") or {}
    states = s.get("pluginState") or {}
    out = []
    for p in PLUGIN_REGISTRY:
        row = dict(p)
        row["enabled"] = bool(enabled.get(p["id"], False))
        st = states.get(p["id"]) or {}
        row["configured"] = bool(st.get("configured", False))
        row["installStatus"] = st.get("installStatus", "not-configured")
        row["installMsg"] = st.get("installMsg", "")
        row["features"] = st.get("features") or {
            f["id"]: bool(f.get("default", False)) for f in p.get("features") or []}
        row["featuresList"] = p.get("features") or []
        row["config"] = st.get("config") or {}
        out.append(row)
    return out


def _plugin_installed(runtime: dict, data_dir: Path) -> bool:
    """检测插件运行环境是否就绪：优先校验克隆目录（git clone 类插件，需目录存在且含标识文件，
    避免克隆中断留下的空目录被误判为已安装），否则查 PATH 可执行文件。"""
    d = runtime.get("dir")
    if d:
        check = runtime.get("checkFile") or ".git"
        return (data_dir / d).is_dir() and (data_dir / d / check).exists()
    return shutil.which(runtime.get("bin", "")) is not None


def _run_install(runtime: dict, data_dir: Path) -> tuple[str, str]:
    """执行自动安装（列表参数、无 shell、超时 180s，克隆类在 data 目录下落地）；
    返回 (installStatus, msg)。失败消息附带可操作的排查步骤（§R20-1）。

    Windows 下 git 会派生持有管道子进程，直接 subprocess.run(timeout=) 超时后
    communicate() 仍可能挂起；故用 Popen + 超时后 taskkill /T /F 递归终止进程树再收尾。
    """
    cmd = list(runtime.get("install") or [])
    if not cmd:
        return "failed", "未配置自动安装命令"
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, cwd=str(data_dir), creationflags=creationflags)
        try:
            out, _ = proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill()
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                               capture_output=True)
            out, _ = proc.communicate()
            return "failed", (
                f"安装超时（180s）。排查：① 网络较慢或依赖较大，可手动执行「{' '.join(cmd)}」；"
                f"② 安装完成后重新点击一键配置。")
        tail = (out or "").strip()[-400:]
        if proc.returncode == 0 and _plugin_installed(runtime, data_dir):
            return "installed", "自动安装完成：" + " ".join(cmd)
        return "failed", (
            f"自动安装失败(exit={proc.returncode})：{tail or '详见终端'}。"
            f"排查：① 手动执行「{' '.join(cmd)}」查看完整报错；"
            f"② 确认网络可访问对应源（npm registry / GitHub / PyPI）；"
            f"③ 权限不足时请以管理员终端重试。")
    except FileNotFoundError:
        return "failed", (
            f"无法执行安装命令 {runtime.get('manager', '')}：请先安装 {runtime.get('manager', '')} 并确保已加入 PATH。"
            f"排查：命令行执行 {runtime.get('manager', '')} -v 验证。")


def _providers_view(s: dict) -> list[dict]:
    """脱敏视图：apiKey 只保留掩码，供前端展示。"""
    out = []
    for p in s.get("providers") or []:
        row = {k: p.get(k) for k in PROVIDER_FIELDS if k in p}
        row["apiKeyMasked"] = mask_key(p.get("apiKey", ""))
        row["apiKey"] = None
        out.append(row)
    return out


def _inject_active_key(s: dict, cfg: Config) -> None:
    """激活 provider 的 Key 注入环境变量（LLMProvider 的 env 兜底路径）。"""
    providers = s.get("providers") or []
    aid = s.get("activeProviderId")
    key = ""
    for p in providers:
        if p.get("id") == aid and p.get("enabled", True):
            key = p.get("apiKey", "")
            break
    if key:
        os.environ[cfg.provider.api_key_env] = key
    else:
        os.environ.pop(cfg.provider.api_key_env, None)


def _next_id(s: dict) -> str:
    from datetime import datetime
    import uuid
    return f"p_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:4]}"


class SettingsBody(CamelModel):
    api_key: Optional[str] = Field(default=None, max_length=512)
    search_api_key: Optional[str] = Field(default=None, max_length=512)
    deep_search_default: Optional[bool] = None
    watermark_default: Optional[str] = Field(default=None, pattern="^(formal|practice)$")


class ProviderBody(CamelModel):
    id: Optional[str] = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    api_key: Optional[str] = Field(default=None, max_length=512)
    capabilities: str = Field(default="text", max_length=64)
    enabled: bool = True


class TestBody(CamelModel):
    base_url: str = Field(min_length=1, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=1, max_length=512)


class PluginBody(CamelModel):
    enabled: bool


@router.get("", response_model=dict)
def get_settings(request: Request):
    s = request.app.state.storage.load_settings()
    key = s.get("apiKey", "")
    skey = s.get("searchApiKey", "")
    providers = s.get("providers") or []
    # 旧版单 Key 迁移：无 providers 时折叠为一条默认配置（便于前端展示/管理）
    if not providers and key:
        providers = [{
            "id": "p_default", "name": "DeepSeek（默认）",
            "baseUrl": request.app.state.config.provider.base_url,
            "model": request.app.state.config.provider.model,
            "apiKey": key, "capabilities": "text", "enabled": True, "order": 0,
        }]
        s["providers"] = providers
        s["activeProviderId"] = "p_default"
        request.app.state.storage.save_settings(s)
    return {"code": 0, "message": "ok", "data": {
        "hasKey": bool(key),
        "apiKeyMasked": mask_key(key),
        "searchHasKey": bool(skey),
        "searchApiKeyMasked": mask_key(skey),
        "deepSearchDefault": bool(s.get("deepSearchDefault", True)),
        "watermarkDefault": s.get("watermarkDefault", "formal"),
        "providers": _providers_view(s),
        "activeProviderId": s.get("activeProviderId", ""),
        "plugins": _plugins_view(s),
    }}


@router.put("", response_model=dict)
def put_settings(body: SettingsBody, request: Request):
    storage = request.app.state.storage
    cfg = request.app.state.config
    s = storage.load_settings()
    if body.api_key is not None:
        key = body.api_key.strip()
        s["apiKey"] = key
        # 同步为默认 provider（无 providers 时），保证生成链路可用
        if key:
            os.environ[cfg.provider.api_key_env] = key
        else:
            os.environ.pop(cfg.provider.api_key_env, None)
    if body.search_api_key is not None:
        skey = body.search_api_key.strip()
        s["searchApiKey"] = skey
        if skey:
            os.environ[cfg.search.api_key_env] = skey
        else:
            os.environ.pop(cfg.search.api_key_env, None)
    if body.deep_search_default is not None:
        s["deepSearchDefault"] = body.deep_search_default
    if body.watermark_default is not None:
        s["watermarkDefault"] = body.watermark_default
    storage.save_settings(s)
    return {"code": 0, "message": "ok", "data": {
        "hasKey": bool(s.get("apiKey", "")),
        "apiKeyMasked": mask_key(s.get("apiKey", "")),
    }}


@router.put("/providers", response_model=dict)
def upsert_provider(body: ProviderBody, request: Request):
    """新增 / 更新 provider（body.apiKey 留空 = 更新时保留原 Key）。"""
    storage = request.app.state.storage
    cfg = request.app.state.config
    s = storage.load_settings()
    providers = s.get("providers") or []

    if body.id:
        target = next((p for p in providers if p.get("id") == body.id), None)
        if not target:
            raise AppError(40001, f"provider 不存在: {body.id}", {"id": body.id})
        target.update({
            "name": body.name.strip(), "baseUrl": body.base_url.strip(),
            "model": body.model.strip(), "capabilities": body.capabilities.strip() or "text",
            "enabled": body.enabled,
        })
        if body.api_key is not None and body.api_key.strip():
            target["apiKey"] = body.api_key.strip()
        pid = body.id
    else:
        pid = _next_id(s)
        providers.append({
            "id": pid, "name": body.name.strip(), "baseUrl": body.base_url.strip(),
            "model": body.model.strip(), "apiKey": (body.api_key or "").strip(),
            "capabilities": body.capabilities.strip() or "text",
            "enabled": body.enabled, "order": len(providers),
        })
    s["providers"] = providers
    # 新增配置 → 自动激活（用户刚配置的 Key 立即生效）；更新当前激活项 → 保持激活
    if not body.id or s.get("activeProviderId") == body.id:
        s["activeProviderId"] = pid
    storage.save_settings(s)
    _inject_active_key(s, cfg)
    return {"code": 0, "message": "ok", "data": {
        "providers": _providers_view(s),
        "activeProviderId": s.get("activeProviderId", ""),
    }}


@router.delete("/providers/{provider_id}", response_model=dict)
def delete_provider(provider_id: str, request: Request):
    storage = request.app.state.storage
    cfg = request.app.state.config
    s = storage.load_settings()
    providers = s.get("providers") or []
    keep = [p for p in providers if p.get("id") != provider_id]
    if len(keep) == len(providers):
        raise AppError(40001, f"provider 不存在: {provider_id}", {"id": provider_id})
    s["providers"] = keep
    if s.get("activeProviderId") == provider_id:
        # 删除激活项 → 自动指向剩余第一个启用项
        s["activeProviderId"] = next((p.get("id") for p in keep if p.get("enabled", True)), "")
    storage.save_settings(s)
    _inject_active_key(s, cfg)
    return {"code": 0, "message": "ok", "data": {
        "providers": _providers_view(s),
        "activeProviderId": s.get("activeProviderId", ""),
    }}


@router.post("/providers/{provider_id}/activate", response_model=dict)
def activate_provider(provider_id: str, request: Request):
    storage = request.app.state.storage
    cfg = request.app.state.config
    s = storage.load_settings()
    providers = s.get("providers") or []
    if not any(p.get("id") == provider_id for p in providers):
        raise AppError(40001, f"provider 不存在: {provider_id}", {"id": provider_id})
    s["activeProviderId"] = provider_id
    storage.save_settings(s)
    _inject_active_key(s, cfg)
    return {"code": 0, "message": "ok", "data": {
        "providers": _providers_view(s),
        "activeProviderId": s.get("activeProviderId", ""),
    }}


@router.post("/providers/test", response_model=dict)
async def test_provider(body: TestBody, request: Request):
    """配置自检：向 Base URL 发一次最小 chat 请求，验证 Key / 模型可用。"""
    payload = {
        "model": body.model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=6) as client:  # 测试连接最多等 6s
            r = await client.post(
                f"{body.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {body.api_key}"},
                json=payload,
            )
            r.raise_for_status()
            return {"code": 0, "message": "ok", "data": {"ok": True}}
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        return {"code": 0, "message": "ok", "data": {"ok": False, "error": str(exc)}}


@router.put("/plugins/{plugin_id}", response_model=dict)
def toggle_plugin(plugin_id: str, body: PluginBody, request: Request):
    """第二层：手动勾选启用/停用插件（精细控制，不与一键配置冲突）。"""
    storage = request.app.state.storage
    s = storage.load_settings()
    _plugin_or_404(plugin_id)
    enabled = s.setdefault("pluginsEnabled", {})
    enabled[plugin_id] = body.enabled
    storage.save_settings(s)
    return {"code": 0, "message": "ok", "data": {"plugins": _plugins_view(s)}}


class FeatureBody(CamelModel):
    enabled: bool


@router.put("/plugins/{plugin_id}/features/{feature_id}", response_model=dict)
def toggle_feature(plugin_id: str, feature_id: str, body: FeatureBody, request: Request):
    """第二层：功能模块级精细控制（单模块启用/停用）。"""
    storage = request.app.state.storage
    p = _plugin_or_404(plugin_id)
    if not any(f["id"] == feature_id for f in p.get("features") or []):
        raise AppError(40001, f"功能模块不存在: {feature_id}", {"pluginId": plugin_id, "featureId": feature_id})
    s = storage.load_settings()
    state = s.setdefault("pluginState", {}).setdefault(plugin_id, {})
    feats = state.setdefault("features", {})
    feats[feature_id] = body.enabled
    storage.save_settings(s)
    return {"code": 0, "message": "ok", "data": {"plugins": _plugins_view(s)}}


@router.post("/plugins/{plugin_id}/configure", response_model=dict)
def configure_plugin(plugin_id: str, request: Request, auto_install: bool = True):
    """第一层：一键配置——依赖环境检测 → 自动安装 → 默认参数写入 → 基础功能预激活。

    幂等可重复执行；auto_install=False 仅检测不安装（供测试/预检）；安装失败时
    configured=False 并返回带排查步骤的手动指引。
    配置成功 ≠ 自动启用（§R20-2）：是否启用由用户在「启用」勾选处自主决定。
    """
    storage = request.app.state.storage
    p = _plugin_or_404(plugin_id)
    s = storage.load_settings()
    state = s.setdefault("pluginState", {}).setdefault(plugin_id, {})
    runtime = p.get("runtime") or {}
    data_dir = storage.root
    name = p.get("name", plugin_id)

    # 1) 依赖环境检测（克隆目录 / PATH 可执行文件）
    installed = _plugin_installed(runtime, data_dir)
    status, msg = ("installed", "运行环境已就绪") if installed else (None, "")

    # 2) 自动安装（缺依赖、开启 auto_install 且存在包管理器时）
    if not installed and auto_install:
        manager = shutil.which(runtime.get("manager", ""))
        if not manager:
            status, msg = "failed", (
                f"缺少包管理器 {runtime.get('manager', '')}，请先安装后重试。"
                f"排查：命令行执行 {runtime.get('manager', '')} -v 验证。")
        else:
            status, msg = _run_install(runtime, data_dir)
            installed = status == "installed"
    elif not installed and not auto_install:
        status, msg = "failed", f"未检测到 {name} 运行环境（自动安装已跳过）。点击「一键配置」执行自动安装。"

    # 3) 默认参数写入 + 基础功能预激活（features 按注册表 default 预勾选）
    state["config"] = dict(p.get("defaultConfig") or {})
    state["features"] = {f["id"]: bool(f.get("default", False)) for f in p.get("features") or []}
    state["installStatus"] = status
    state["installMsg"] = msg
    state["configured"] = bool(installed)
    if installed:
        state["installTime"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    storage.save_settings(s)
    return {"code": 0, "message": "ok", "data": {"plugins": _plugins_view(s)}}
