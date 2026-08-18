"""match_agent LLM 抽象（mock/real 骨架）。

D13（2026-08-14 已确认）：**不提供无 Key 降级**——LLM Key 为前置必要条件，
配置缺失即报错（拒绝服务），与运行时异常兜底（decide/evaluate 失败→规则降级）区分。

P0 线性链无 LLM 判定，本模块仅提供骨架：
- `LLMClient`：统一 chat_json 入口（OpenAI 兼容）；mock 模式返回固定 JSON。
- `resolve_llm(backend, api_key)`：按 backend 构造客户端，Key 缺失时抛 LLMKeyError。
- `safe_json_loads(text)`：健壮 JSON 解析（代码块剥离/平衡区间截取/常见损坏修复），
  供 chat_json 消费，LLM 返回格式不规范时不直接失败（2026-08-15 新增）。
"""
from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


class LLMKeyError(RuntimeError):
    """LLM Key 缺失/非法（前置必要条件，D13）。"""


def _strip_fences(text: str) -> str:
    """剥离 ```json ... ``` / ``` ... ``` 代码块围栏。"""
    m = _JSON_FENCE.search(text)
    return m.group(1).strip() if m else text.strip()


def _balanced_region(text: str) -> str:
    """截取首个 { } 或 [ ] 平衡区间（丢弃前后说明文字/截断尾巴）。"""
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == open_ch:
                depth += 1
            elif text[i] == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return text


def _repair_common(text: str) -> str:
    """常见损坏修复：BOM、多余尾逗号、简单单引号键/值。"""
    text = text.lstrip("\ufeff")
    text = re.sub(r",(\s*[}\]])", r"\1", text)  # 尾逗号
    text = re.sub(r"'([^']*)'", r'"\1"', text)  # 单引号 → 双引号（粗粒度，仅作兜底）
    return text


def safe_json_loads(text: str) -> tuple[Any, bool]:
    """健壮 JSON 解析：围栏剥离 → 平衡区间截取 → 原样 loads → 修复重试。

    返回 (obj, repaired)；完全无法解析时返回 (None, False)，由调用方决定
    降级策略（不在此抛异常，保留原文供日志排查）。
    """
    if not text or not isinstance(text, str):
        return None, False
    candidates: list[str] = []
    stripped = _strip_fences(text)
    balanced = _balanced_region(stripped)
    for cand in (text, stripped, balanced, _repair_common(stripped),
                 _repair_common(balanced)):
        if not cand or cand in candidates:
            continue
        candidates.append(cand)
        try:
            obj = json.loads(cand)
            # 顶层是数组（LLM 直接返回 items 列表）→ 归一化为 {"items": [...]}
            if isinstance(obj, list):
                obj = {"items": obj}
            return obj, True
        except (json.JSONDecodeError, ValueError):
            continue
    return None, False


def diagnose_json(text: str) -> list[str]:
    """解析失败原因分类诊断（供日志/统计快速定位格式问题）。

    返回特征列表；无法归入已知类别时给「无法分类」兜底。
    """
    if not text or not isinstance(text, str):
        return ["空输入/非字符串"]
    issues: list[str] = []
    stripped = _strip_fences(text)
    if stripped != text.strip():
        issues.append("围栏剥离后仍失败")
    balanced = _balanced_region(stripped)
    if balanced and balanced != stripped:
        issues.append("平衡区间提取候选失败")
    opens = text.count("{") + text.count("[")
    closes = text.count("}") + text.count("]")
    if opens != closes:
        issues.append(f"括号不平衡（开{opens}/闭{closes}，疑似截断）")
    if re.search(r",\s*[}\]]", text):
        issues.append("存在尾逗号")
    if "'" in text and '"' not in text.replace("'", ""):
        issues.append("存在单引号键值")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
        issues.append("含控制字符")
    if "{" not in text and "[" not in text:
        issues.append("无 JSON 结构（无 {} 或 []）")
    return issues or ["无法分类（候选全部解析失败）"]


class LLMClient:
    """统一 LLM 客户端。real 走 OpenAI 兼容 /chat/completions；mock 返回占位。"""

    def __init__(self, backend: str = "mock", api_key: str = "", model: str = "") -> None:
        self.backend = backend
        self.api_key = api_key
        self.model = model
        if backend == "real":
            if not api_key:
                raise LLMKeyError(
                    "LLM Key 为前置必要条件（D13）：real 模式必须提供 api_key，不提供无 Key 降级"
                )
            if not model:
                raise LLMKeyError("real 模式必须提供 model")

    def chat_json(self, system: str, user: str, *, max_tokens: int = 2000,
                  temperature: float = 0.3) -> tuple[dict[str, Any], dict[str, Any]]:
        """调用 LLM 并解析 JSON。返回 (obj, meta)。

        real 路径经 safe_json_loads 健壮解析（围栏剥离/平衡截取/修复重试）；
        完全无法解析时抛 ValueError（含原文片段，供日志排查）——调用方按 D7 降级。
        """
        if self.backend == "mock":
            obj = {"__mock__": True, "input_preview": user[:80]}
            return obj, {"backend": "mock", "model": self.model}
        return self._chat_real(system, user, max_tokens=max_tokens, temperature=temperature)

    def _chat_real(self, system: str, user: str, *, max_tokens: int,
                   temperature: float) -> tuple[dict[str, Any], dict[str, Any]]:
        import urllib.request

        base = self.model.split(":")[0] if ":" in self.model else self.model
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            f"https://api.{'deepseek' if base.startswith('deepseek') else 'openai'}.com/v1/chat/completions"
            if "://" not in self.model else self.model,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        obj, repaired = safe_json_loads(content)
        if obj is None:
            issues = "；".join(diagnose_json(content))
            raise ValueError(
                f"LLM 返回无法解析为 JSON（{issues}）：原文前 200 字符：{content[:200]}")
        return obj, {"backend": "real", "model": self.model, "json_repaired": repaired}


def resolve_llm(backend: str = "mock", api_key: str = "",
                model: str = "") -> LLMClient:
    """按 backend 构造 LLM 客户端；Key 前置校验（D13）。"""
    return LLMClient(backend=backend, api_key=api_key, model=model)
