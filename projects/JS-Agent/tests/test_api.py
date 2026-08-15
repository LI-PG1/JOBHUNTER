"""v0.2 API 冒烟测试（FastAPI TestClient，不依赖网络/真实 Key）。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["version"] == "0.2.0"


def test_console_status():
    resp = client.get("/api/console/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["constraint_mode"] in ("strict", "standard", "loose")
    assert data["constraint_preset"]["match_accept"] > 0
    # 预设厂商清单（15 家，含 DeepSeek 规范化命名）
    providers = data["providers"]
    assert len(providers) >= 15
    ids = {p["id"] for p in providers}
    assert {"deepseek", "zhipu", "openai", "ollama"} <= ids
    ds = next(p for p in providers if p["id"] == "deepseek")
    assert "DeepSeek-V4-Flash" in ds["models"]
    assert "DeepSeek-V4-Pro" in ds["models"]


def test_console_key_validation():
    """无 Key 情况下：保存缺字段 400 / 未知厂商 400 / 非法模型 400。"""
    resp = client.post("/api/console/keys", json={})
    assert resp.status_code == 400
    resp = client.post("/api/console/keys", json={"provider_id": "nope", "model": "X", "api_key": "k"})
    assert resp.status_code == 400
    resp = client.post("/api/console/keys", json={"provider_id": "deepseek", "model": "不存在的模型", "api_key": "k"})
    assert resp.status_code == 400


def test_console_constraint():
    resp = client.post("/api/console/constraint", json={"mode": "loose"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "loose"
    resp = client.post("/api/console/constraint", json={"mode": "bad"})
    assert resp.status_code == 400
    # 恢复
    client.post("/api/console/constraint", json={"mode": "strict"})


def test_match_validation():
    """画像过短 / 城市缺失 / 非法条数 → 400。"""
    resp = client.post("/api/match", json={"profile_text": "太短", "city": "深圳", "max_results": 20})
    assert resp.status_code == 400
    resp = client.post("/api/match", json={"profile_text": "这是一段超过二十个字的画像描述内容用于测试", "city": "", "max_results": 20})
    assert resp.status_code == 400
    resp = client.post("/api/match", json={"profile_text": "这是一段超过二十个字的画像描述内容用于测试", "city": "深圳", "max_results": 7})
    assert resp.status_code == 400


def test_match_no_key_400(monkeypatch):
    """无任何 API Key 时快速失败（400），不再异步空转。"""
    from app.config import key_store
    monkeypatch.setattr(key_store, "load", lambda: {})
    resp = client.post("/api/match", json={"profile_text": "这是一段超过二十个字的画像描述内容用于测试", "city": "深圳", "max_results": 20})
    assert resp.status_code == 400
    assert "API Key" in resp.json()["detail"]


def test_match_provider_key_missing_400(monkeypatch):
    """指定厂商但未配置 Key → 400。"""
    from app.config import key_store
    monkeypatch.setattr(key_store, "load", lambda: {"deepseek": {"model": "DeepSeek-V4-Flash", "api_key": ""}})
    resp = client.post("/api/match", json={
        "profile_text": "这是一段超过二十个字的画像描述内容用于测试", "city": "深圳",
        "max_results": 20, "provider_id": "deepseek",
    })
    assert resp.status_code == 400
    assert "deepseek" in resp.json()["detail"]


def test_match_unknown_job_404():
    resp = client.get("/api/match/notexist")
    assert resp.status_code == 404


def test_plugins_status():
    resp = client.get("/api/console/plugins")
    assert resp.status_code == 200
    data = resp.json()
    assert "components" in data
    assert "ddgs" in data["components"]
    assert "trafilatura" in data["components"]
    assert "playwright" in data["components"]
    assert data["busy"] is None
