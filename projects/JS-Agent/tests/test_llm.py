"""LLM 客户端单元测试（mock 网络层，不真实调用）。"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest import mock

import pytest

from app.core.errors import LLMError, ProviderNotConfiguredError
from app.core.llm import LLMClient


class FakeResp:
    """模拟 urllib 响应（with 上下文）。"""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResp":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def make_client(keys: dict | None = None) -> LLMClient:
    """注入内存 Key，避免读取真实 KeyStore。"""
    c = LLMClient()
    c._keys = keys
    return c


def ok_payload(content: str) -> FakeResp:
    return FakeResp(
        json.dumps({"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 10}}).encode("utf-8")
    )


KEYS = {"deepseek": {"model": "DeepSeek-V4-Flash", "api_key": "sk-test"}}


# ---------- 成功路径 ----------

def test_all_providers_have_model_map():
    """命名规范：每个预设厂商的每个显示名必须映射官方 API 名（openai_compat 模板除外）。"""
    from app.config import PROVIDERS

    for pid, prov in PROVIDERS.items():
        if pid == "openai_compat":
            continue
        assert "model_map" in prov, f"{pid} 缺少 model_map"
        assert len(prov["model_map"]) == len(prov["models"]), f"{pid} model_map 与 models 数量不一致"
        for m in prov["models"]:
            assert m in prov["model_map"], f"{pid} 显示名 {m} 未映射官方 API 名"


@mock.patch("urllib.request.urlopen")
def test_chat_success(urlopen):
    urlopen.return_value = ok_payload('{"a":1}')
    r = make_client(KEYS).chat("sys", "user")
    assert r["content"] == '{"a":1}'
    assert r["provider"] == "deepseek"
    assert r["model"] == "DeepSeek-V4-Flash"
    assert r["usage"]["total_tokens"] == 10


@mock.patch("urllib.request.urlopen")
def test_chat_model_map_applied(urlopen):
    """显示名 DeepSeek-V4-Flash 发送时应映射为官方模型名 deepseek-v4-flash。"""
    urlopen.return_value = ok_payload('{"a":1}')
    r = make_client(KEYS).chat("sys", "user", "deepseek", "DeepSeek-V4-Flash")
    sent = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert sent["model"] == "deepseek-v4-flash"
    # 返回的 model 保持显示名（前端一致性）
    assert r["model"] == "DeepSeek-V4-Flash"


@mock.patch("urllib.request.urlopen")
def test_chat_no_map_keeps_model(urlopen):
    """未配置 model_map 的厂商（openai_compat 模板）保持原模型名发送。"""
    urlopen.return_value = ok_payload('{"a":1}')
    c = make_client({"openai_compat": {"model": "my-gateway-model", "api_key": "x"}})
    c.chat("sys", "user", "openai_compat", "my-gateway-model")
    sent = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert sent["model"] == "my-gateway-model"


@mock.patch("urllib.request.urlopen")
def test_test_provider_uses_map(urlopen, monkeypatch):
    """测试连通时同样应用 model_map（test_provider 读取磁盘 KeyStore，mock 掉避免依赖环境）。"""
    from app.core.llm import key_store

    monkeypatch.setattr(key_store, "load", lambda: {"deepseek": {"model": "DeepSeek-V4-Flash", "api_key": "sk-test"}})
    urlopen.return_value = FakeResp(b'{"ok":true}')
    r = make_client(KEYS).test_provider("deepseek", "DeepSeek-V4-Flash")
    sent = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert sent["model"] == "deepseek-v4-flash"
    assert r["ok"] is True


@mock.patch("urllib.request.urlopen")
def test_chat_json_ok(urlopen):
    urlopen.return_value = ok_payload(json.dumps({"skills": [{"name": "vLLM"}]}))
    obj, meta = make_client(KEYS).chat_json("sys", "user")
    assert obj == {"skills": [{"name": "vLLM"}]}
    assert meta["provider"] == "deepseek"


@mock.patch("urllib.request.urlopen")
def test_chat_json_code_fence(urlopen):
    """兼容模型输出 ```json 围栏。"""
    urlopen.return_value = ok_payload('```json\n{"ok": true}\n```')
    obj, _ = make_client(KEYS).chat_json("sys", "user")
    assert obj == {"ok": True}


# ---------- 错误路径 ----------

def test_no_key_raises():
    """无任何可用 Key → ProviderNotConfiguredError（不联网）。"""
    with pytest.raises(ProviderNotConfiguredError):
        make_client({}).chat("sys", "user")


@mock.patch("urllib.request.urlopen")
def test_provider_specified_no_key(urlopen):
    """指定厂商但未配置该厂商 Key。"""
    with pytest.raises(ProviderNotConfiguredError):
        make_client(KEYS).chat("sys", "user", provider_id="openai", model="GPT-4o-mini")


@mock.patch("urllib.request.urlopen")
def test_unknown_provider(urlopen):
    with pytest.raises(LLMError, match="未知厂商"):
        make_client({"nope": {"model": "X", "api_key": "k"}}).chat("sys", "user", provider_id="nope", model="X")


@mock.patch("urllib.request.urlopen")
def test_chat_json_invalid(urlopen):
    """模型返回非 JSON 文本 → LLMError。"""
    urlopen.return_value = ok_payload("这不是 JSON")
    with pytest.raises(LLMError, match="JSON 输出解析失败"):
        make_client(KEYS).chat_json("sys", "user")


@mock.patch("urllib.request.urlopen")
def test_chat_http_error(urlopen):
    """HTTP 4xx/5xx（如 Key 无效）。"""
    urlopen.side_effect = urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, io.BytesIO(b'{"error":"bad key"}'))
    with pytest.raises(LLMError, match="401"):
        make_client(KEYS).chat("sys", "user")


@mock.patch("urllib.request.urlopen")
def test_chat_network_error(urlopen):
    """网络不可达。"""
    urlopen.side_effect = urllib.error.URLError("connection refused")
    with pytest.raises(LLMError, match="网络错误"):
        make_client(KEYS).chat("sys", "user")


@mock.patch("urllib.request.urlopen")
def test_chat_response_parse_error(urlopen):
    """响应缺少 choices/message 结构。"""
    urlopen.return_value = FakeResp(b'{"unexpected": true}')
    with pytest.raises(LLMError, match="响应解析失败"):
        make_client(KEYS).chat("sys", "user")
