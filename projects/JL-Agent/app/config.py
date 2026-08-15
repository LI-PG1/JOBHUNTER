"""配置加载：.env + config.json（缺失时回退 config.example.json 作默认）。"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Paths:
    data_dir: str = "data"
    rules_dir: str = "rules"
    templates_dir: str = "templates"


@dataclass
class ProviderCfg:
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    model: str = "deepseek-v4-flash"


@dataclass
class SearchApiCfg:
    provider: str = "tavily"
    api_key_env: str = "TAVILY_API_KEY"
    interval_seconds: float = 1.1


@dataclass
class Limits:
    education_max: int = 3
    internship_max: int = 2
    jobs_max: int = 5
    photo_max_bytes: int = 5 * 1024 * 1024


@dataclass
class Config:
    provider: ProviderCfg = field(default_factory=ProviderCfg)
    search: SearchApiCfg = field(default_factory=SearchApiCfg)
    paths: Paths = field(default_factory=Paths)
    limits: Limits = field(default_factory=Limits)


def _get(d: dict, key: str, default):
    v = d.get(key)
    return default if v is None else v


def load_config() -> Config:
    load_dotenv(PROJECT_ROOT / ".env")
    cfg_file = PROJECT_ROOT / "config.json"
    if not cfg_file.exists():
        cfg_file = PROJECT_ROOT / "config.example.json"
    raw = json.loads(cfg_file.read_text(encoding="utf-8"))

    cfg = Config()
    p = raw.get("provider") or {}
    cfg.provider = ProviderCfg(
        base_url=_get(p, "base_url", cfg.provider.base_url),
        api_key_env=_get(p, "api_key_env", cfg.provider.api_key_env),
        model=_get(p, "model", cfg.provider.model),
    )
    s = raw.get("search", {}).get("api") or {}
    cfg.search = SearchApiCfg(**s) if s else cfg.search
    if raw.get("paths"):
        cfg.paths = Paths(**raw["paths"])
    # EXE 打包场景（onefile 临时目录会漂移）：通过 JL_AGENT_DATA 将数据目录重定向到固定位置
    data_env = os.environ.get("JL_AGENT_DATA")
    if data_env:
        cfg.paths.data_dir = data_env
    if raw.get("limits"):
        cfg.limits = Limits(**raw["limits"])
    return cfg


def api_key(cfg: Config) -> str:
    """从环境变量取真实密钥（.env 注入）。"""
    return os.getenv(cfg.provider.api_key_env, "")


def mask_key(key: str) -> str:
    """脱敏展示：sk-1234****5678。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]
