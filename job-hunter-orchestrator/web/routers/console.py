"""/api/console —— 用户控制台（API Key 管理 / CLI 工具）。

- GET  /api/console                      读取配置与 Key 列表（脱敏）及工具状态
- POST /api/console/key                  新增 API Key
- PUT  /api/console/key/{id}             启用 / 停用（启用互斥：同一时间仅一个启用，并同步 .env）
- DELETE /api/console/key/{id}           移除 Key（若移除的是当前启用项，自动启用剩余第一个）
- POST /api/console/test                 连通性测试：按厂商真实 URL 调一次最小请求
- POST /api/console/tool                 新增自定义 CLI/MCP 工具
- PUT  /api/console/tool/{id}            更新自定义工具 / 启停任意工具
- DELETE /api/console/tool/{id}          删除自定义工具（预置仅可禁用）
- POST /api/console/tool/{id}/install    一键配置：安装预置工具依赖并启用
- POST /api/console/tool/{id}/uninstall  一键卸载：卸载预置工具依赖并停用
"""
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from tools.cli_tool import PRESET_TOOLS

router = APIRouter()

BASE = Path(__file__).resolve().parent.parent.parent  # D:\Drivers\JobMaker
ENV_FILE = BASE / ".env"
KEYS_FILE = BASE / "web" / "api_keys.json"
TOOLS_FILE = BASE / "web" / "tools.json"

# 厂商 → OpenAI 兼容 base URL（与前端 PROVIDER_MODELS 的 key 对齐）
PROVIDER_BASE_URL = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "kimi": "https://api.moonshot.cn/v1",
    "claude": "https://api.anthropic.com/v1",
    "ollama": "http://127.0.0.1:11434/v1",
}


def _read_env() -> Dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    out: Dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _write_env(data: Dict[str, str]) -> None:
    # 保留原注释，仅更新键值
    lines: list[str] = []
    keys = set(data)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            strip = line.strip()
            if strip and not strip.startswith("#") and "=" in strip:
                k = strip.split("=", 1)[0].strip()
                if k in keys:
                    lines.append(f"{k}={data[k]}")
                    keys.discard(k)
                    continue
            lines.append(line)
    for k in keys:
        lines.append(f"{k}={data[k]}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_keys() -> List[Dict[str, Any]]:
    """api_keys.json：{keys: [{id, provider, model, api_key, enabled, created_at}]}"""
    if KEYS_FILE.exists():
        try:
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            return data.get("keys", [])
        except json.JSONDecodeError:
            pass
    return []


def _save_keys(keys: List[Dict[str, Any]]) -> None:
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps({"keys": keys}, ensure_ascii=False, indent=2), encoding="utf-8")


def _mask_key(k: str) -> str:
    k = str(k or "")
    return (k[:6] + "****" + k[-4:]) if len(k) > 12 else "****"


def _migrate_legacy_env_key(keys: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """首次升级：把 .env 中已配置的 LLM_API_KEY 迁入 keys.json（仅一次）。"""
    if keys:
        return keys
    env = _read_env()
    if not env.get("LLM_API_KEY") or not env.get("LLM_MODEL"):
        return keys
    keys.append({
        "id": "k_" + str(int(time.time() * 1000)),
        "provider": env.get("LLM_PROVIDER", ""),
        "model": env["LLM_MODEL"],
        "api_key": env["LLM_API_KEY"],
        "enabled": True,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    _save_keys(keys)
    return keys


def _public_key(k: Dict[str, Any]) -> Dict[str, Any]:
    """脱敏后返回给前端。"""
    return {**k, "api_key": _mask_key(k.get("api_key", ""))}


def _sync_env_from_keys(keys: List[Dict[str, Any]]) -> None:
    """把当前启用的 Key 同步写入 .env，供 ai.py / ai/test 等读取。"""
    enabled = next((k for k in keys if k.get("enabled")), None)
    env = _read_env()
    if enabled:
        env["LLM_API_KEY"] = enabled.get("api_key", "")
        if enabled.get("model"):
            env["LLM_MODEL"] = enabled["model"]
        if enabled.get("provider"):
            env["LLM_PROVIDER"] = enabled["provider"]
            if enabled["provider"] in PROVIDER_BASE_URL:
                env["LLM_BASE_URL"] = PROVIDER_BASE_URL[enabled["provider"]]
    else:
        env.pop("LLM_API_KEY", None)
    _write_env(env)


def _load_tools_file() -> Dict[str, Any]:
    """tools.json：{state: {id: {enabled}}, custom: [自定义工具定义]}"""
    if TOOLS_FILE.exists():
        try:
            return json.loads(TOOLS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"state": {}, "custom": []}


def _save_tools_file(data: Dict[str, Any]) -> None:
    TOOLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOOLS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _all_tools() -> List[Dict[str, Any]]:
    """预置库 + 自定义合并，附 enabled / preset / installed 标记。"""
    tf = _load_tools_file()
    state = tf.get("state", {})
    out: List[Dict[str, Any]] = []
    for t in PRESET_TOOLS:
        st = state.get(t["id"], {})
        out.append({**t, "preset": True, "enabled": bool(st.get("enabled", True)),
                    "installed": bool(st.get("installed", False))})
    for t in tf.get("custom", []):
        out.append({**t, "preset": False, "enabled": bool(state.get(t["id"], {}).get("enabled", True))})
    return out


@router.get("/console")
def get_console() -> Dict[str, Any]:
    env = _read_env()
    keys = _migrate_legacy_env_key(_load_keys())
    return {
        "mode": "real",
        "key_configured": bool(env.get("LLM_API_KEY")),
        "llm_model": env.get("LLM_MODEL", ""),
        "llm_provider": env.get("LLM_PROVIDER", ""),
        "keys": [_public_key(k) for k in keys],
        "tools": _all_tools(),
    }


@router.post("/console/key")
def add_key(body: Dict[str, Any]) -> Dict[str, Any]:
    """新增 API Key；首个 Key 自动启用，其余默认停用待手动启用。"""
    key = str(body.get("api_key") or "").strip()
    model = str(body.get("model") or "").strip()
    provider = str(body.get("provider") or "").strip()
    if provider != "ollama" and not key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    if not model:
        raise HTTPException(status_code=400, detail="请先选择模型")
    if provider not in PROVIDER_BASE_URL:
        raise HTTPException(status_code=400, detail=f"未知厂商: {provider}")
    keys = _load_keys()
    k = {
        "id": "k_" + str(int(time.time() * 1000)),
        "provider": provider,
        "model": model,
        "api_key": key,
        "enabled": len(keys) == 0,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    keys.append(k)
    _save_keys(keys)
    _sync_env_from_keys(keys)
    return {"ok": True, "key": _public_key(k), "keys": [_public_key(x) for x in keys]}


@router.put("/console/key/{key_id}")
def update_key(key_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """启用 / 停用 Key；启用时互斥（其余全部停用）并同步 .env。"""
    keys = _load_keys()
    target = next((k for k in keys if k["id"] == key_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="未知 Key")
    if "enabled" in body:
        if body["enabled"]:
            for k in keys:
                k["enabled"] = k["id"] == key_id
        else:
            target["enabled"] = False
    _save_keys(keys)
    _sync_env_from_keys(keys)
    return {"ok": True, "keys": [_public_key(x) for x in keys]}


@router.delete("/console/key/{key_id}")
def delete_key(key_id: str) -> Dict[str, Any]:
    """移除 Key；若移除的是当前启用项，自动启用剩余第一个。"""
    keys = _load_keys()
    target = next((k for k in keys if k["id"] == key_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="未知 Key")
    was_enabled = bool(target.get("enabled"))
    keys = [k for k in keys if k["id"] != key_id]
    if was_enabled and keys:
        keys[0]["enabled"] = True
    _save_keys(keys)
    _sync_env_from_keys(keys)
    return {"ok": True, "keys": [_public_key(x) for x in keys]}


@router.post("/console/test")
def test_connection(body: Dict[str, Any]) -> Dict[str, Any]:
    """连通性测试：按厂商真实 URL 发一次最小请求，验证 key + 模型组合真实可用。

    支持两种入参：key_id（用已存 Key 的真实值测试）或 provider/model/api_key 直接测试。
    """
    if body.get("key_id"):
        k = next((x for x in _load_keys() if x["id"] == body["key_id"]), None)
        if not k:
            raise HTTPException(status_code=404, detail="未知 Key")
        provider, model, key = k["provider"], k["model"], k.get("api_key", "")
    else:
        provider = str(body.get("provider") or "").strip()
        model = str(body.get("model") or "").strip()
        key = str(body.get("api_key") or "").strip()
    base = PROVIDER_BASE_URL.get(provider, "")
    if not base:
        return {"ok": False, "error": f"未知厂商: {provider}"}
    if not model:
        return {"ok": False, "error": "请先选择模型", "base_url": base}
    if provider != "ollama" and not key:
        return {"ok": False, "error": "API Key 不能为空", "base_url": base}
    payload = {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
    start = time.time()
    try:
        if provider == "claude":  # Anthropic 走 /v1/messages，非 OpenAI 兼容
            url = base.rstrip("/") + "/messages"
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "x-api-key": key,
                         "anthropic-version": "2023-06-01"},
            )
        else:
            url = base.rstrip("/") + "/chat/completions"
            headers = {"Content-Type": "application/json"}
            if provider != "ollama":
                headers["Authorization"] = f"Bearer {key}"
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        return {"ok": True, "base_url": base, "model": model,
                "latency_ms": int((time.time() - start) * 1000)}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode(errors="ignore")[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {e.code}", "base_url": base, "model": model,
                "detail": detail}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"网络错误: {e.reason}", "base_url": base, "model": model}
    except Exception as e:
        return {"ok": False, "error": str(e), "base_url": base, "model": model}


@router.post("/console/tool")
def add_tool(body: Dict[str, Any]) -> Dict[str, Any]:
    """新增自定义 CLI/MCP 工具。"""
    name = str(body.get("name") or "").strip()
    cmd = str(body.get("command") or "").strip()
    if not name or not cmd:
        raise HTTPException(status_code=400, detail="工具名与命令均不能为空")
    tf = _load_tools_file()
    tool_id = "custom_" + str(int(__import__("time").time() * 1000))
    custom = {
        "id": tool_id,
        "name": name,
        "type": str(body.get("type") or "cli").strip() or "cli",
        "command": cmd,
        "desc": str(body.get("desc") or "").strip(),
    }
    tf.setdefault("custom", []).append(custom)
    tf.setdefault("state", {})[tool_id] = {"enabled": True}
    _save_tools_file(tf)
    return {"ok": True, "tool": {**custom, "preset": False, "enabled": True}}


@router.put("/console/tool/{tool_id}")
def update_tool(tool_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """启停任意工具；更新自定义工具定义。"""
    tf = _load_tools_file()
    state = tf.setdefault("state", {})
    if "enabled" in body:
        st = state.setdefault(tool_id, {})
        st["enabled"] = bool(body["enabled"])
    custom_list = tf.setdefault("custom", [])
    idx = next((i for i, t in enumerate(custom_list) if t["id"] == tool_id), None)
    if idx is not None:
        if body.get("name") is not None:
            custom_list[idx]["name"] = str(body["name"]).strip() or custom_list[idx]["name"]
        if body.get("command") is not None:
            custom_list[idx]["command"] = str(body["command"]).strip() or custom_list[idx]["command"]
        if body.get("type") is not None:
            custom_list[idx]["type"] = str(body["type"]).strip()
        if body.get("desc") is not None:
            custom_list[idx]["desc"] = str(body["desc"]).strip()
    _save_tools_file(tf)
    tool = next((t for t in _all_tools() if t["id"] == tool_id), None)
    if not tool:
        raise HTTPException(status_code=404, detail=f"未知工具: {tool_id}")
    return {"ok": True, "tool": tool}


@router.delete("/console/tool/{tool_id}")
def delete_tool(tool_id: str) -> Dict[str, Any]:
    """删除自定义工具（预置工具仅可禁用，不可删除）。"""
    tf = _load_tools_file()
    if any(t["id"] == tool_id for t in PRESET_TOOLS):
        raise HTTPException(status_code=403, detail="预置工具不可删除，可通过启停开关禁用")
    custom_list = tf.setdefault("custom", [])
    before = len(custom_list)
    tf["custom"] = [t for t in custom_list if t["id"] != tool_id]
    if len(tf["custom"]) == before:
        raise HTTPException(status_code=404, detail=f"未知工具: {tool_id}")
    tf.get("state", {}).pop(tool_id, None)
    _save_tools_file(tf)
    return {"ok": True, "id": tool_id}


def _run_tool_dep(tool_id: str, action: str) -> Dict[str, Any]:
    """一键配置 / 一键卸载：执行预置工具的依赖安装/卸载命令并更新状态。"""
    tool = next((t for t in PRESET_TOOLS if t["id"] == tool_id), None)
    if not tool:
        raise HTTPException(status_code=404, detail=f"未知预置工具: {tool_id}")
    cmd = tool.get("install") if action == "install" else tool.get("uninstall")
    if not cmd:
        raise HTTPException(status_code=400, detail="该工具没有可用的安装/卸载命令")
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=502, detail="命令执行超时（600s）")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"执行失败：{exc}") from exc
    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=(proc.stderr or proc.stdout or "命令失败")[-500:])
    tf = _load_tools_file()
    st = tf.setdefault("state", {}).setdefault(tool_id, {})
    st["installed"] = action == "install"
    if action == "install":
        st["enabled"] = True
    _save_tools_file(tf)
    return {"ok": True, "id": tool_id, "action": action, "summary": (proc.stdout or "").strip()[-300:]}


@router.post("/console/tool/{tool_id}/install")
def install_tool(tool_id: str) -> Dict[str, Any]:
    return _run_tool_dep(tool_id, "install")


@router.post("/console/tool/{tool_id}/uninstall")
def uninstall_tool(tool_id: str) -> Dict[str, Any]:
    return _run_tool_dep(tool_id, "uninstall")
