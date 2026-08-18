"""轻量 OpenAI 兼容 LLM 直连客户端（供工具 real 模式与匹配路由复用）。

设计要点（适配「点击即用」单仓库交付）：
- 不依赖外部子项目 / 中间服务，直接调用大模型（OpenAI 兼容 /chat/completions）；
- 每次调用重读项目根 .env，控制台新增/切换 API Key 即时生效，无需重启；
- 只依赖标准库 urllib（requirements 无额外负担）。
"""
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


class LLMKeyError(RuntimeError):
    """未配置/未启用 API Key"""


def _read_env() -> Dict[str, str]:
    """读取 .env（dotenv 兼容的简单键值解析，保留引号剥离）。"""
    out: Dict[str, str] = {}
    try:
        for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def resolve_llm() -> Dict[str, str]:
    """返回启用的 LLM 配置；未配置抛 LLMKeyError。"""
    env = _read_env()
    key = (env.get("LLM_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    if not key:
        raise LLMKeyError("未配置 API Key，请先在控制台「API Key」中添加并启用")
    return {
        "key": key,
        "base": (env.get("LLM_BASE_URL") or os.getenv("LLM_BASE_URL")
                 or "https://api.deepseek.com").rstrip("/"),
        "model": (env.get("LLM_MODEL") or os.getenv("LLM_MODEL")
                  or "deepseek-v4-flash"),
    }


def chat_json(system: str, user: str, max_tokens: int = 2000,
              temperature: float = 0.3) -> Dict[str, Any]:
    """单轮对话并要求返回严格 JSON（提示词约束 + 围栏剥离，兼容各厂商）。

    异常：LLMKeyError（未配 Key）、RuntimeError（网络/HTTP）、ValueError（非 JSON）。
    """
    cfg = resolve_llm()
    body = json.dumps({
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    base = cfg["base"]
    url = base if base.endswith("/chat/completions") else base + "/chat/completions"
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['key']}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"LLM 调用失败: HTTP {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM 网络错误: {e.reason}") from e
    content = (data["choices"][0]["message"]["content"] or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM 返回非 JSON: {content[:200]}") from e
