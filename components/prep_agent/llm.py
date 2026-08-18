"""prep_agent LLM 客户端（生成 + D3 审核共用）。

与 match_agent/llm.py 同风格：D13 决策——real 模式无 Key 即报错（前置必要条件，不提供无 Key 降级）。
区别：prep 主要需要 chat_text（生成 markdown / 审核结论），JSON 入口仅作兜底。
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"


class LLMKeyError(RuntimeError):
    """LLM Key 缺失/非法（前置必要条件，D13）。"""


class LLMClient:
    """统一 LLM 客户端。real 走 OpenAI 兼容 /chat/completions；mock 返回占位文本。"""

    def __init__(self, backend: str = "mock", api_key: str = "",
                 model: str = "", base_url: str = "") -> None:
        self.backend = backend
        self.api_key = api_key
        self.model = model or ("" if backend == "mock" else DEFAULT_MODEL)
        self.base_url = base_url or ("" if backend == "mock" else DEFAULT_BASE_URL)
        if backend == "real":
            if not api_key:
                raise LLMKeyError(
                    "LLM Key 为前置必要条件（D13）：real 模式必须提供 api_key，不提供无 Key 降级")
            if not model:
                raise LLMKeyError("real 模式必须提供 model")

    def chat_text(self, system: str, user: str, *, max_tokens: int = 4096,
                  temperature: float = 0.5) -> str:
        """调用 LLM 返回文本（生成材料 / 审核结论）。"""
        if self.backend == "mock":
            return "（mock）\n## " + user.strip().splitlines()[0][:40]
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = self.base_url.rstrip("/") + "/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()

    def chat_json(self, system: str, user: str, *, max_tokens: int = 2000,
                  temperature: float = 0.3) -> tuple[dict[str, Any], dict[str, Any]]:
        """调用 LLM 并解析 JSON。返回 (obj, meta)。"""
        if self.backend == "mock":
            return {"__mock__": True, "input_preview": user[:80]}, {"backend": "mock"}
        text = self.chat_text(system, user, max_tokens=max_tokens,
                              temperature=temperature)
        return safe_json_loads(text)


def resolve_llm(cfg: dict[str, Any] | None = None) -> LLMClient:
    """按配置构造 LLM 客户端；Key 前置校验（D13）。cfg 可来自大脑 state.llm。"""
    cfg = cfg or {}
    return LLMClient(
        backend=cfg.get("backend", "mock"),
        api_key=cfg.get("api_key", ""),
        model=cfg.get("model", ""),
        base_url=cfg.get("base_url", ""),
    )


def _strip_fences(text: str) -> str:
    import re
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    return m.group(1).strip() if m else text.strip()


def safe_json_loads(text: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """健壮 JSON 解析：围栏剥离 → 平衡区间截取 → 修复重试。"""
    if not text or not isinstance(text, str):
        return None, {"error": "空输入"}
    import re
    stripped = _strip_fences(text)
    balanced = ""
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = stripped.find(open_ch)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(stripped)):
            if stripped[i] == open_ch:
                depth += 1
            elif stripped[i] == close_ch:
                depth -= 1
                if depth == 0:
                    balanced = stripped[start:i + 1]
                    break
    candidates = [text, stripped, balanced,
                  re.sub(r",(\s*[}\]])", r"\1", stripped)]
    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        try:
            obj = json.loads(cand)
            if isinstance(obj, list):
                obj = {"items": obj}
            return obj, {"repaired": cand != stripped}
        except (json.JSONDecodeError, ValueError):
            continue
    return None, {"error": "无法解析为 JSON"}
