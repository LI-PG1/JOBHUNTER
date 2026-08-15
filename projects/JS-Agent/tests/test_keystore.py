"""KeyStore 加密落盘测试（save→load 往返、明文不落盘、异常容错）。"""
from __future__ import annotations

import json

from app.config import KeyStore


def test_roundtrip_encrypted(tmp_path):
    """save 后 load 能还原明文 Key，且磁盘文件不含明文。"""
    path = tmp_path / "keys.json"
    ks = KeyStore(path)
    ks.save({"deepseek": {"model": "DeepSeek-V4-Flash", "api_key": "sk-super-secret"}})
    raw = path.read_text(encoding="utf-8")
    assert "sk-super-secret" not in raw  # 绝不落明文
    assert '"key_enc"' in raw
    data = ks.load()
    assert data["deepseek"]["api_key"] == "sk-super-secret"
    assert data["deepseek"]["model"] == "DeepSeek-V4-Flash"


def test_missing_file_empty(tmp_path):
    assert KeyStore(tmp_path / "nope.json").load() == {}


def test_corrupt_file_empty(tmp_path):
    path = tmp_path / "keys.json"
    path.write_text("{ 这不是合法 JSON", encoding="utf-8")
    assert KeyStore(path).load() == {}


def test_tampered_key_skipped(tmp_path):
    """key_enc 被篡改导致解密失败 → 跳过该厂商，不崩溃、不返回明文。"""
    path = tmp_path / "keys.json"
    ks = KeyStore(path)
    ks.save({"deepseek": {"model": "DeepSeek-V4-Flash", "api_key": "sk-1"}, "zhipu": {"model": "GLM-4.7-Flash", "api_key": "sk-2"}})
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["zhipu"]["key_enc"] = "AAAAAAA"  # 篡改
    path.write_text(json.dumps(raw), encoding="utf-8")
    data = ks.load()
    assert data["deepseek"]["api_key"] == "sk-1"
    assert "api_key" not in data.get("zhipu", {})  # 被跳过
