"""LLM 客户端：多厂商统一接口（预设厂商，OpenAI 兼容协议）。

- 厂商/模型命名严格遵循 config.PROVIDERS 规范
- Key 从 KeyStore 读取（加密落盘）
- JSON 模式优先（response_format=json_object）
- 兼容推理模型：响应含 reasoning_content 时仅取 content
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from ..config import PROVIDERS, key_store
from ..core.errors import LLMError, ProviderNotConfiguredError


class LLMClient:
    def __init__(self) -> None:
        self._keys: dict[str, dict[str, Any]] | None = None

    @staticmethod
    def _resolve_model(prov: dict[str, Any], model: str) -> str:
        """显示名 → 厂商 API 真实模型名（未配置映射则原样发送）。"""
        return prov.get("model_map", {}).get(model, model)

    def _reload_keys(self) -> dict[str, dict[str, Any]]:
        self._keys = key_store.load()
        return self._keys

    def get_active_provider(self, preferred: str | None = None) -> tuple[str, str] | None:
        """返回首个可用 (provider_id, model) 或按偏好优先。"""
        keys = self._keys if self._keys is not None else self._reload_keys()
        order = [preferred] + [p for p in keys if p != preferred] if preferred else list(keys)
        for pid in order:
            entry = keys.get(pid)
            if not entry:
                continue
            model = entry.get("model")
            if entry.get("api_key") and model:
                return pid, model
        return None

    def chat(
        self,
        system: str,
        user: str,
        provider_id: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        json_mode: bool = True,
        timeout: int = 180,
    ) -> dict[str, Any]:
        """调用 LLM，返回 {"content", "provider", "model", "usage", "elapsed_s"}。

        provider_id/model 缺省时自动选可用厂商；若均未配置抛 ProviderNotConfiguredError。
        """
        if provider_id is None or model is None:
            active = self.get_active_provider(provider_id)
            if active is None:
                raise ProviderNotConfiguredError("未配置可用的大模型 API Key，请先到控制台配置")
            provider_id, model = active

        prov = PROVIDERS.get(provider_id)
        if prov is None:
            raise LLMError(f"未知厂商: {provider_id}")
        keys = self._keys if self._keys is not None else self._reload_keys()
        entry = keys.get(provider_id) or {}
        api_key = entry.get("api_key", "")
        if not api_key:
            raise ProviderNotConfiguredError(f"厂商 {prov['name']} 未配置 Key")

        body: dict[str, Any] = {
            "model": self._resolve_model(prov, model),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if prov.get("json_mode") and json_mode:
            body["response_format"] = {"type": "json_object"}
        # 推理模型默认带思考（占 max_tokens，可能导致输出被截断为空），JSON 任务按预设关闭
        if prov.get("disable_thinking"):
            body["thinking"] = {"type": "disabled"}

        req = urllib.request.Request(
            prov["base_url"],
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise LLMError(f"LLM 调用失败 [{exc.code}] {prov['name']}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"LLM 网络错误 {prov['name']}: {exc.reason}") from exc

        try:
            data = json.loads(raw.decode("utf-8"))
            msg = data["choices"][0]["message"]
            content = msg.get("content", "")
            usage = data.get("usage", {})
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise LLMError(f"LLM 响应解析失败 {prov['name']}: {exc}") from exc

        return {
            "content": content,
            "provider": provider_id,
            "model": model,
            "usage": usage,
            "elapsed_s": round(time.time() - t0, 2),
        }

    def chat_json(
        self,
        system: str,
        user: str,
        provider_id: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: int = 180,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """返回 (json对象, 调用元信息)。解析失败抛 LLMError。"""
        resp = self.chat(system, user, provider_id, model, temperature, max_tokens, json_mode=True, timeout=timeout)
        text = resp["content"].strip()
        if not text:
            raise LLMError("LLM 输出为空（推理思考可能占满 max_tokens，或模型未返回内容）")
        if text.startswith("```"):
            text = text.strip("`")
            start = text.find("{")
            if start >= 0:
                text = text[start:]
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM JSON 输出解析失败: {exc}\n原文: {text[:200]}") from exc
        return obj, resp

    def test_provider(self, provider_id: str, model: str) -> dict[str, Any]:
        """连通性自检（短请求，兼容推理模型 reasoning 占 token）。"""
        return self._test_with(provider_id, model, self._reload_keys().get(provider_id, {}).get("api_key", ""))

    def test_provider_with(self, provider_id: str, api_key: str, model: str) -> dict[str, Any]:
        """用临时 Key 自检（不落盘）。"""
        return self._test_with(provider_id, model, api_key)

    def _test_with(self, provider_id: str, model: str, api_key: str) -> dict[str, Any]:
        if not api_key or not model:
            return {"ok": False, "model": model, "error": "缺少 Key 或模型"}
        try:
            prov = PROVIDERS.get(provider_id)
            if prov is None:
                return {"ok": False, "error": f"未知厂商: {provider_id}"}
            body = {
                "model": self._resolve_model(prov, model),
                "messages": [{"role": "user", "content": '回复 JSON: {"status":"ok"}'}],
                "max_tokens": 64,
                "temperature": 0,
            }
            if prov.get("json_mode"):
                body["response_format"] = {"type": "json_object"}
            req = urllib.request.Request(
                prov["base_url"],
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
            return {"ok": True, "model": model, "elapsed_s": round(time.time() - t0, 2)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": model, "error": str(exc)}


llm = LLMClient()
