"""控制台服务：厂商 Key 管理 + 模型选择 + 状态聚合（方案 v0.5 §3/§8.3）。

- 预设厂商清单（config.PROVIDERS），Key 加密落盘（KeyStore）
- testProvider 自检连通性（短请求）
- 成本统计已移除
"""
from __future__ import annotations

from typing import Any

from .config import PROVIDERS, config, key_store
from .core.llm import llm


class ConsoleService:
    def list_providers(self) -> list[dict[str, Any]]:
        """预设厂商 + 当前配置状态（不含 Key 明文）。"""
        keys = key_store.load()
        out: list[dict[str, Any]] = []
        for pid, prov in PROVIDERS.items():
            entry = keys.get(pid, {})
            out.append({
                "id": pid,
                "name": prov["name"],
                "models": prov["models"],
                "note": prov.get("note", ""),
                "has_key": bool(entry.get("api_key")),
                "model": entry.get("model", ""),
                "enabled": bool(entry.get("enabled", entry.get("api_key", ""))),
            })
        return out

    def save_key(self, provider_id: str, model: str, api_key: str, enabled: bool = True) -> dict[str, Any]:
        if provider_id not in PROVIDERS:
            raise ValueError(f"未知厂商: {provider_id}")
        if model not in PROVIDERS[provider_id]["models"]:
            raise ValueError(f"模型 {model} 不在厂商 {provider_id} 预设清单中")
        keys = key_store.load()
        keys[provider_id] = {"model": model, "api_key": api_key, "enabled": enabled}
        key_store.save(keys)
        # 刷新搜索通道探测（智谱 Key 变化影响搜索后端）
        try:
            from .plugins.search import search_plugin
            search_plugin.refresh()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "provider_id": provider_id, "model": model}

    def delete_key(self, provider_id: str) -> dict[str, Any]:
        keys = key_store.load()
        keys.pop(provider_id, None)
        key_store.save(keys)
        return {"ok": True}

    def test_provider(self, provider_id: str, model: str) -> dict[str, Any]:
        return llm.test_provider(provider_id, model)

    def set_constraint(self, mode: str) -> dict[str, Any]:
        if mode not in ("strict", "standard", "loose"):
            raise ValueError("约束强度必须是 strict/standard/loose")
        config.constraint_mode = mode
        config.save()
        return {"ok": True, "mode": mode}

    def status(self) -> dict[str, Any]:
        providers = self.list_providers()
        try:
            from .plugins.registry import plugin_manager
            plugins = plugin_manager.status()
        except Exception as exc:  # noqa: BLE001
            plugins = {"error": str(exc)}
        return {
            "constraint_mode": config.constraint_mode,
            "constraint_preset": config.constraints,
            "providers": providers,
            "plugins": plugins,
        }


console_service = ConsoleService()
