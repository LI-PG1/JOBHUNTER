"""LLM provider 适配层（契约 §1/§5.3）：OpenAI 兼容接口，JSON 模式支持。

- 默认 DeepSeek（config.json / .env）。
- 设置控制台（§5.4）可管理多 provider（name/baseUrl/model/apiKey/capabilities/enabled），
  激活项优先于默认配置，实现「打破单平台局限、多模型切换」。
"""
from typing import Optional

import httpx

from ..config import Config, api_key
from .errors import AppError, E_LLM


class LLMProvider:
    def __init__(self, cfg: Config, storage=None):
        self.cfg = cfg
        self.storage = storage  # 可选：本地设置仓（多 provider 时读取激活项）

    def active(self) -> Optional[dict]:
        """从本地设置解析当前激活的 provider；无配置时回退默认（cfg.provider + env）。"""
        if not self.storage:
            return None
        try:
            s = self.storage.load_settings()
        except Exception:
            return None
        providers = s.get("providers") or []
        aid = s.get("activeProviderId")
        for p in providers:
            if p.get("id") == aid and p.get("enabled", True) and p.get("apiKey"):
                return p
        for p in providers:
            if p.get("enabled", True) and p.get("apiKey"):
                return p
        return None

    @property
    def ready(self) -> bool:
        if self.active():
            return True
        return bool(api_key(self.cfg))

    async def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        p = self.active()
        base_url = (p or {}).get("baseUrl") or self.cfg.provider.base_url
        model = (p or {}).get("model") or self.cfg.provider.model
        key = (p or {}).get("apiKey") or api_key(self.cfg)
        if not key:
            raise AppError(E_LLM, "未配置模型 API Key（见设置控制台或 .env）")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(E_LLM, f"LLM 调用失败: {exc}") from exc
