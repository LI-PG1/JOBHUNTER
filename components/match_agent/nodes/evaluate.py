"""match_agent 搜索结果评估器（evaluate 节点）。

设计依据：《JS搜索回路详细设计.md §3.3》
- `EVALUATE_SYSTEM`：LLM 结果评估提示词
- `evaluate()`：主入口。LLM 批量评估 → 校验对齐 → 非法/失败降级规则评估
- `rule_fallback_evaluation()`：规则降级评估器（URL 去重 + is_job 规则）
- `verdict_for()`：结果判定（add / merge / discard），供调用方收录

收录规则（文档 §3.3）：
- keep=true 且 novelty != duplicate → 收录（add）
- novelty=seen（URL 已存在但信息更全）→ 合并更新（merge）
- quality=low 且非招聘页（is_job=false）→ 丢弃（discard）
"""

from __future__ import annotations

import json
from typing import Any, Callable

NOVELTIES = ("new", "seen", "duplicate")
QUALITIES = ("high", "medium", "low")

EVALUATE_SYSTEM = (
    "你是岗位匹配系统的「搜索结果评估器」。给定本轮搜索结果（JSON 数组），逐条评估并输出严格 JSON：\n"
    '{"items":[{"index":0,"novelty":"new|seen|duplicate","quality":"high|medium|low",'
    '"keep":true,"reason":"判定理由(≤30字)"}]}\n'
    "判定规则：\n"
    "1. novelty：new=与已收录条目无重复的新结果；seen=URL 已存在但信息更全（可合并更新）；"
    "duplicate=与已收录完全重复；\n"
    "2. quality：high=招聘岗位页且信息完整（标题/公司/JD 摘要可用）；medium=疑似招聘页但信息不全；"
    "low=非招聘页（百科/新闻/无关页面）；\n"
    "3. keep：是否值得收录（quality=high 或 medium 且非重复时 true）；\n"
    "4. index 必须与输入数组下标一一对应，不得遗漏或新增；\n"
    "5. 严禁编造输入中不存在的信息。"
)


def build_batch_input(raw_items: list[dict[str, Any]]) -> str:
    """构造评估批量输入（保留 title/url/snippet/date，供 LLM 判定）。"""
    batch = [
        {
            "title": i.get("title", ""),
            "url": i.get("url", ""),
            "snippet": (i.get("snippet") or "")[:300],
            "date": i.get("date", ""),
        }
        for i in raw_items
    ]
    return json.dumps(batch, ensure_ascii=False)


def verdict_for(novelty: str, quality: str, keep: bool, is_job: bool = True) -> str:
    """结果判定：add / merge / discard（文档 §3.3 收录规则）。"""
    if not keep:
        return "discard"
    if novelty == "duplicate":
        return "discard"
    if novelty == "seen":
        return "merge"
    if quality == "low" and not is_job:
        return "discard"
    return "add"


def rule_single(item: dict[str, Any], existing_urls: set[str]) -> dict[str, Any]:
    """单条规则评估（LLM 缺失条目 / 降级时使用）。"""
    url = item.get("url", "")
    is_job = bool(item.get("is_job", True))
    novelty = "seen" if url and url in existing_urls else "new"
    quality = "high" if is_job else "low"
    keep = is_job
    return {
        "novelty": novelty,
        "quality": quality,
        "keep": keep,
        "verdict": verdict_for(novelty, quality, keep, is_job),
        "reason": "规则评估",
    }


def rule_fallback_evaluation(raw_items: list[dict[str, Any]],
                             existing_urls: set[str]) -> list[dict[str, Any]]:
    """规则降级评估器：URL 去重判定 novelty + is_job 洗涤标记判定 quality/keep。"""
    return [{**item, "_eval": rule_single(item, existing_urls)} for item in raw_items]


def _validate_llm_output(obj: Any, count: int) -> tuple[dict[int, dict[str, Any]] | None, str]:
    """校验 LLM 评估输出，返回 (index → eval, error)。结构非法返回 (None, error)。"""
    if not isinstance(obj, dict):
        return None, "评估输出不是 JSON 对象"
    items = obj.get("items")
    if not isinstance(items, list):
        return None, "评估输出缺少 items 数组"
    parsed: dict[int, dict[str, Any]] = {}
    for e in items:
        if not isinstance(e, dict):
            continue
        idx = e.get("index")
        if not isinstance(idx, int) or not (0 <= idx < count):
            continue
        novelty = e.get("novelty")
        quality = e.get("quality")
        keep = e.get("keep")
        if novelty not in NOVELTIES or quality not in QUALITIES or not isinstance(keep, bool):
            continue
        parsed[idx] = {"novelty": novelty, "quality": quality, "keep": keep,
                       "reason": str(e.get("reason", ""))}
    return parsed, ""


def evaluate(
    raw_items: list[dict[str, Any]],
    existing_urls: set[str],
    *,
    llm_call: Callable[..., tuple[dict[str, Any], dict[str, Any]]],
    provider_id: str | None = None,
    model: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """evaluate 节点主入口。

    返回 (annotated_items, meta)：
    - annotated_items：原条目 + `_eval`（novelty/quality/keep/verdict/reason）
    - meta：degraded / error / llm_called（供 trace 记录）
    """
    meta: dict[str, Any] = {"degraded": False, "error": "", "llm_called": True}
    if not raw_items:
        return [], meta

    batch = build_batch_input(raw_items)
    try:
        obj, _ = llm_call(EVALUATE_SYSTEM, batch, provider_id, model, max_tokens=2000)
    except Exception as exc:  # noqa: BLE001  # LLM 失败 → 全量规则降级
        meta.update(degraded=True, error=f"LLM 调用失败: {exc}", llm_called=False)
        return rule_fallback_evaluation(raw_items, existing_urls), meta

    parsed, err = _validate_llm_output(obj, len(raw_items))
    if err or parsed is None:
        meta.update(degraded=True, error=f"评估输出非法: {err or '结构缺失'}")
        return rule_fallback_evaluation(raw_items, existing_urls), meta
    if not parsed:
        # LLM 输出无任何有效条目 → 视为解析失败，全量降级（部分缺失才走逐条规则补）
        meta.update(degraded=True, error="LLM 评估输出无有效条目")
        return rule_fallback_evaluation(raw_items, existing_urls), meta

    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw_items):
        e = parsed.get(i) or rule_single(item, existing_urls)  # LLM 漏条目 → 规则补
        e = dict(e)
        e["verdict"] = verdict_for(e["novelty"], e["quality"], e["keep"], item.get("is_job", True))
        out.append({**item, "_eval": e})
    return out, meta
