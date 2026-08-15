"""控制台 API：预设厂商/Key 管理 + 插件双按钮 + 约束强度。"""
from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException

from ..console import console_service
from ..core.llm import llm
from ..plugins.auto_deploy import start_configure, start_uninstall

router = APIRouter(prefix="/api/console", tags=["console"])

# 插件操作互斥（后端锁，配合前端双按钮置灰）
_plugin_lock = threading.Lock()


@router.get("/status")
async def status() -> dict[str, Any]:
    return console_service.status()


@router.post("/keys")
async def save_key(req: dict[str, Any]) -> dict[str, Any]:
    pid = str(req.get("provider_id", ""))
    model = str(req.get("model", ""))
    api_key = str(req.get("api_key", "")).strip()
    if not pid or not model or not api_key:
        raise HTTPException(status_code=400, detail="厂商/模型/Key 均为必填")
    try:
        return console_service.save_key(pid, model, api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/keys/{provider_id}")
async def delete_key(provider_id: str) -> dict[str, Any]:
    return console_service.delete_key(provider_id)


@router.post("/keys/{provider_id}/test")
async def test_key(provider_id: str, req: dict[str, Any] | None = None) -> dict[str, Any]:
    """测试已保存或新填的 Key。req 可选 {api_key, model}。"""
    model = str((req or {}).get("model") or "")
    if req and req.get("api_key"):
        # 临时测试：不落盘
        return llm.test_provider_with(provider_id, str(req["api_key"]), model)
    keys = console_service.list_providers()
    entry = next((p for p in keys if p["id"] == provider_id), None)
    if not entry or not entry.get("has_key"):
        raise HTTPException(status_code=400, detail="该厂商未配置 Key")
    return console_service.test_provider(provider_id, entry.get("model") or "")


@router.post("/constraint")
async def set_constraint(req: dict[str, Any]) -> dict[str, Any]:
    mode = str(req.get("mode", ""))
    try:
        return console_service.set_constraint(mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/plugins")
async def plugins_status() -> dict[str, Any]:
    from ..plugins.registry import plugin_manager
    return plugin_manager.status()


@router.post("/plugins/configure")
async def plugins_configure() -> dict[str, Any]:
    """一键配置全部：后台执行，按钮置灰由前端根据 busy 状态控制。"""
    ok = start_configure()
    if not ok:
        raise HTTPException(status_code=409, detail="插件操作进行中，请稍候")
    return {"ok": True, "status": "configuring"}


@router.post("/plugins/uninstall")
async def plugins_uninstall() -> dict[str, Any]:
    """一键卸载全部。"""
    ok = start_uninstall()
    if not ok:
        raise HTTPException(status_code=409, detail="插件操作进行中，请稍候")
    return {"ok": True, "status": "uninstalling"}


@router.post("/plugins/{cid}/configure")
async def plugin_configure(cid: str) -> dict[str, Any]:
    """单个插件配置。"""
    ok = start_configure(cid)
    if not ok:
        raise HTTPException(status_code=409, detail="插件操作进行中，请稍候")
    return {"ok": True, "status": "configuring", "cid": cid}


@router.post("/plugins/{cid}/uninstall")
async def plugin_uninstall(cid: str) -> dict[str, Any]:
    """单个插件卸载。"""
    ok = start_uninstall(cid)
    if not ok:
        raise HTTPException(status_code=409, detail="插件操作进行中，请稍候")
    return {"ok": True, "status": "uninstalling", "cid": cid}
