"""JS-Agent v0.2 配置：预设厂商清单 + 存储 + 约束强度。

设计要点（方案 v0.5）：
- 厂商采用预设机制（15 家），不允许用户自定义，命名严格规范
- Key 加密落盘（storage/keys.json）：Windows DPAPI / 其他平台 Fernet
- 成本统计已移除
"""
from __future__ import annotations

import json
import os
import sys
import ctypes
import base64
from pathlib import Path
from typing import Any

from .core.errors import JSAgentError

BASE_DIR = Path(__file__).resolve().parent.parent


def _writable_root() -> Path:
    """可写数据根目录：PyInstaller 打包后为 exe 同级（用户有写权限），源码运行时为项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return BASE_DIR


# 打包后（frozen）：BASE_DIR 指向 _MEIPASS（只读资产 rules/frontend），数据写入 WRITABLE_DIR/storage
WRITABLE_DIR = _writable_root()


# ---------- 预设厂商清单（规范化命名，不可自定义） ----------

# 厂商 id → 显示名 / OpenAI 兼容 chat 端点 / 是否支持 JSON 模式
PROVIDERS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "models": ["DeepSeek-V4-Flash", "DeepSeek-V4-Pro"],
        "model_map": {"DeepSeek-V4-Flash": "deepseek-v4-flash", "DeepSeek-V4-Pro": "deepseek-v4-pro"},
        "json_mode": True,
        "disable_thinking": True,  # v4 系列默认带推理思考（占 max_tokens），JSON 任务关闭思考避免输出被截断
        "note": "低价，默认推荐",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "models": ["GLM-4.7-Flash", "GLM-4V-Flash", "GLM-5"],
        "model_map": {"GLM-4.7-Flash": "glm-4.7-flash", "GLM-4V-Flash": "glm-4v-flash", "GLM-5": "glm-5"},
        "json_mode": True,
        "note": "内置 web_search 工具（搜索首选）",
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "models": ["GPT-4o-mini", "GPT-4o"],
        "model_map": {"GPT-4o-mini": "gpt-4o-mini", "GPT-4o": "gpt-4o"},
        "json_mode": True,
    },
    "aliyun": {
        "name": "阿里通义",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "models": ["Qwen-Max", "Qwen-Plus"],
        "model_map": {"Qwen-Max": "qwen-max", "Qwen-Plus": "qwen-plus"},
        "json_mode": True,
        "note": "百炼 WebSearch 可用",
    },
    "baidu": {
        "name": "百度文心",
        "base_url": "https://qianfan.baidubce.com/v2/chat/completions",
        "models": ["ERNIE-4.0-Turbo", "ERNIE-5.1"],
        "model_map": {"ERNIE-4.0-Turbo": "ernie-4.0-turbo-8k", "ERNIE-5.1": "ernie-5.1"},
        "json_mode": True,
    },
    "doubao": {
        "name": "字节豆包",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "models": ["Doubao-Seed-2.1-Pro", "Doubao-Seed-2.1-Turbo"],
        "model_map": {"Doubao-Seed-2.1-Pro": "doubao-seed-2-1-pro-260628", "Doubao-Seed-2.1-Turbo": "doubao-seed-2-1-turbo-260628"},
        "json_mode": True,
    },
    "tencent": {
        "name": "腾讯混元",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
        "models": ["Hunyuan-TurboS"],
        "model_map": {"Hunyuan-TurboS": "hunyuan-turbos-latest"},
        "json_mode": True,
    },
    "moonshot": {
        "name": "月之暗面 Kimi",
        "base_url": "https://api.moonshot.cn/v1/chat/completions",
        "models": ["Kimi-K2.6", "Kimi-K3"],
        "model_map": {"Kimi-K2.6": "kimi-k2.6", "Kimi-K3": "kimi-k3"},
        "json_mode": True,
    },
    "minimax": {
        "name": "MiniMax",
        "base_url": "https://api.minimaxi.com/v1/chat/completions",
        "models": ["MiniMax-M2.7", "MiniMax-M3"],
        "model_map": {"MiniMax-M2.7": "MiniMax-M2.7", "MiniMax-M3": "MiniMax-M3"},
        "json_mode": True,
    },
    "stepfun": {
        "name": "阶跃星辰",
        "base_url": "https://api.stepfun.com/v1/chat/completions",
        "models": ["Step-3.5-Flash", "Step-3.7-Flash"],
        "model_map": {"Step-3.5-Flash": "step-3.5-flash", "Step-3.7-Flash": "step-3.7-flash"},
        "json_mode": True,
    },
    "xiaomi": {
        "name": "小米 MiMo",
        "base_url": "https://api.xiaomimimo.com/v1/chat/completions",
        "models": ["MiMo-V2.5-Pro"],
        "model_map": {"MiMo-V2.5-Pro": "mimo-v2.5-pro"},
        "json_mode": True,
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1/chat/completions",
        "models": ["Claude-Sonnet", "Claude-Haiku"],
        "model_map": {"Claude-Sonnet": "claude-sonnet-4-5", "Claude-Haiku": "claude-haiku-4-5"},
        "json_mode": True,
    },
    "google": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "models": ["Gemini-2.5-Flash"],
        "model_map": {"Gemini-2.5-Flash": "gemini-2.5-flash"},
        "json_mode": True,
    },
    "ollama": {
        "name": "Ollama（本地）",
        "base_url": "http://127.0.0.1:11434/v1/chat/completions",
        "models": ["Qwen2.5", "Llama3.1"],
        "model_map": {"Qwen2.5": "qwen2.5", "Llama3.1": "llama3.1"},
        "json_mode": True,
        "note": "完全离线",
    },
    "openai_compat": {
        "name": "OpenAI 兼容（预置模板）",
        "base_url": "https://your-gateway.example.com/v1/chat/completions",
        "models": ["（按网关配置填写）"],
        "json_mode": True,
        "note": "仅预置接入模板，模型名按规范填写",
    },
}

# 约束强度（可配置）：strict / standard / loose
# 每档含 judge（混合判定）与 search_agent（搜索回路）两个新配置段（改造设计 §4.3）
_CONSTRAINT_EXTRA = {
    "judge": {
        "llm_enabled": True,          # false → 纯规则降级（行为≈改造前）
        "batch_size": 20,             # 软性判定批量（条/批）
        "weights": {"rule": 0.6, "llm": 0.4},
        "dim_weights": {"jd_fit": 0.4, "job_quality": 0.3, "growth": 0.3},
        "hard_city": True, "hard_degree": True, "hard_required_skills": True,
        "required_skill_top": 3,      # 必填技能取画像前 N 个 confirmed 技能
        "use_role_ontology": False,   # 是否启用 roles.json 权重参与（暂未启用）
        "llm_downgrade_cap": 30,      # |rule-llm| 看空仲裁阈值
        "llm_upgrade_floor": 20,      # LLM 看多仲裁阈值
    },
    "search_agent": {
        "enabled": True,              # false → 完全走旧 while 循环
        "max_llm_calls": 12,          # 决策+评估合计 LLM 调用预算（防烧 token）
        "max_queries_per_round": 2,   # 每轮最多 query 数（沿用）
        "evaluator_enabled": True,
    },
}

CONSTRAINT_PRESETS: dict[str, dict[str, Any]] = {
    "strict": {
        "min_search_rounds": 3,
        "max_search_rounds": 10,
        "match_accept": 80,
        "match_gap": 60,
        "match_expand": 90,
        "fresh_days": 60,
        "source_min_types": 3,
        "profile_retry": 2,
        "qa_retry": 3,
        **_CONSTRAINT_EXTRA,
    },
    "standard": {
        "min_search_rounds": 3,
        "max_search_rounds": 8,
        "match_accept": 75,
        "match_gap": 55,
        "match_expand": 90,
        "fresh_days": 90,
        "source_min_types": 2,
        "profile_retry": 2,
        "qa_retry": 3,
        **_CONSTRAINT_EXTRA,
    },
    "loose": {
        "min_search_rounds": 2,
        "max_search_rounds": 6,
        "match_accept": 70,
        "match_gap": 50,
        "match_expand": 85,
        "fresh_days": 120,
        "source_min_types": 1,
        "profile_retry": 1,
        "qa_retry": 2,
        **_CONSTRAINT_EXTRA,
    },
}


class Config:
    def __init__(self) -> None:
        self.rules_dir: Path = BASE_DIR / "rules"
        self.storage_dir: Path = WRITABLE_DIR / "storage"  # 打包后写 exe 同级目录（可写）
        self.host: str = "127.0.0.1"
        self.port: int = 8101
        self.constraint_mode: str = "strict"  # strict/standard/loose
        self.plugins_state: dict[str, Any] = {}
        self._load()

    @property
    def constraints(self) -> dict[str, Any]:
        return CONSTRAINT_PRESETS.get(self.constraint_mode, CONSTRAINT_PRESETS["strict"])

    @property
    def judge(self) -> dict[str, Any]:
        """混合判定配置（改造设计 §4.3 judge 段）。"""
        return self.constraints.get("judge", {})

    @property
    def search_agent(self) -> dict[str, Any]:
        """搜索回路配置（改造设计 §4.3 search_agent 段）。"""
        return self.constraints.get("search_agent", {})

    def _load(self) -> None:
        self.storage_dir.mkdir(exist_ok=True)
        path = WRITABLE_DIR / "config.json"
        if not path.exists():
            return
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        server = data.get("server", {})
        self.host = server.get("host", self.host)
        self.port = int(server.get("port", self.port))
        self.constraint_mode = data.get("constraint_mode", self.constraint_mode)
        self.plugins_state = data.get("plugins", {}) or {}

    def save(self) -> None:
        data = {
            "server": {"host": self.host, "port": self.port},
            "constraint_mode": self.constraint_mode,
            "plugins": self.plugins_state,
        }
        (WRITABLE_DIR / "config.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


config = Config()


# ---------- Key 加密存储（跨平台） ----------

try:
    from cryptography.fernet import Fernet  # 非 Windows 平台加密
except ImportError:  # pragma: no cover
    Fernet = None


class KeyStore:
    """厂商 Key 加密落盘（storage/keys.json）。

    Windows 用系统 DPAPI（零依赖）；Linux/macOS 用 Fernet（密钥文件 ~/.js-agent/secret.key，0600）。
    磁盘上永不保存明文 Key。
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (config.storage_dir / "keys.json")
        self._fernet: Any | None = None

    def _dpapi(self, data: bytes, encrypt: bool) -> bytes:
        """Windows DPAPI CryptProtectData/CryptUnprotectData。"""
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]

        def _blob(b: bytes) -> DATA_BLOB:
            buf = ctypes.create_string_buffer(b, len(b))
            return DATA_BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

        fn = ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
        out = DATA_BLOB()
        in_blob = _blob(data)
        if not fn(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out)):
            raise OSError("DPAPI 操作失败")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)

    def _fernet_cipher(self) -> Any:
        """非 Windows：Fernet 密码器，密钥文件自动生成于用户目录。"""
        if self._fernet is None:
            if Fernet is None:
                raise JSAgentError("当前平台需要 cryptography 支持 Key 加密：pip install cryptography")
            key_path = Path.home() / ".js-agent" / "secret.key"
            if not key_path.exists():
                key_path.parent.mkdir(parents=True, exist_ok=True)
                key_path.write_bytes(Fernet.generate_key())
                try:
                    key_path.chmod(0o600)  # 仅当前用户可读
                except OSError:  # pragma: no cover
                    pass
            self._fernet = Fernet(key_path.read_bytes())
        return self._fernet

    def _encrypt(self, data: bytes) -> bytes:
        if sys.platform == "win32":
            return self._dpapi(data, True)
        return self._fernet_cipher().encrypt(data)

    def _decrypt(self, blob: bytes) -> bytes:
        if sys.platform == "win32":
            return self._dpapi(blob, False)
        return self._fernet_cipher().decrypt(blob)

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            data: dict[str, dict[str, Any]] = {}
            for provider_id, entry in raw.items():
                entry = dict(entry)
                enc = entry.get("key_enc")
                if enc:
                    try:
                        entry["api_key"] = self._decrypt(base64.b64decode(enc)).decode("utf-8")
                    except Exception:  # noqa: BLE001（跨平台换机/密钥失效：跳过该厂商）
                        continue
                data[provider_id] = entry
            return data
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, data: dict[str, dict[str, Any]]) -> None:
        payload: dict[str, dict[str, Any]] = {}
        for provider_id, entry in data.items():
            e = dict(entry)
            if e.get("api_key"):
                e["key_enc"] = base64.b64encode(self._encrypt(e["api_key"].encode("utf-8"))).decode("ascii")
                e.pop("api_key", None)
            payload[provider_id] = e
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


key_store = KeyStore()
