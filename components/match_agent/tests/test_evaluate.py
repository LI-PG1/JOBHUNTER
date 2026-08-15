"""evaluate 评估器的 mock 测试：提示词 / 批量输入 / 结果判定（verdict）/ 规则降级。

运行：python -m tests（match_agent 目录下，自动发现本文件）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nodes"))

from evaluate import (  # noqa: E402
    EVALUATE_SYSTEM, NOVELTIES, QUALITIES,
    build_batch_input, evaluate, rule_fallback_evaluation, verdict_for,
)

# ---------- mock 工具 ----------

ITEMS = [
    {"title": "AI推理工程师-某公司", "url": "https://job1.com/a", "snippet": "负责 vLLM 部署", "date": "2026-08-01", "is_job": True},
    {"title": "某公司官网", "url": "https://corp.com", "snippet": "公司介绍", "date": "", "is_job": False},
    {"title": "AI工程师(重复)", "url": "https://job1.com/a", "snippet": "重复", "date": "", "is_job": True},
]


def _llm_factory(result=None, error=None, calls=None):
    def _mock_llm(system, user, provider_id=None, model=None, max_tokens=None):
        if calls is not None:
            calls.append((system, user))
        if error is not None:
            raise error
        return (result if result is not None else {}), {}
    return _mock_llm


def _llm_items(*evals):
    """构造 LLM 输出 items（index 递增）。"""
    return {"items": [{"index": i, **e} for i, e in enumerate(evals)]}


# ---------- 提示词 ----------

class TestEvaluateSystem(unittest.TestCase):
    def test_prompt_contains_fields(self):
        self.assertIn("novelty", EVALUATE_SYSTEM)
        self.assertIn("quality", EVALUATE_SYSTEM)
        self.assertIn("keep", EVALUATE_SYSTEM)
        self.assertIn("index", EVALUATE_SYSTEM)

    def test_prompt_contains_rules(self):
        self.assertIn("new|seen|duplicate", EVALUATE_SYSTEM)
        self.assertIn("high|medium|low", EVALUATE_SYSTEM)
        self.assertIn("不得遗漏或新增", EVALUATE_SYSTEM)

    def test_enums(self):
        self.assertEqual(NOVELTIES, ("new", "seen", "duplicate"))
        self.assertEqual(QUALITIES, ("high", "medium", "low"))


class TestBuildBatchInput(unittest.TestCase):
    def test_batch_contains_all(self):
        batch = build_batch_input(ITEMS)
        self.assertIn("https://job1.com/a", batch)
        self.assertIn("AI推理工程师-某公司", batch)
        self.assertIn("负责 vLLM 部署", batch)


# ---------- 结果判定（verdict_for） ----------

class TestVerdictFor(unittest.TestCase):
    def test_add(self):
        self.assertEqual(verdict_for("new", "high", True, True), "add")
        self.assertEqual(verdict_for("new", "medium", True, True), "add")

    def test_keep_false_discard(self):
        self.assertEqual(verdict_for("new", "high", False, True), "discard")

    def test_duplicate_discard(self):
        self.assertEqual(verdict_for("duplicate", "high", True, True), "discard")

    def test_seen_merge(self):
        self.assertEqual(verdict_for("seen", "high", True, True), "merge")

    def test_low_and_not_job_discard(self):
        self.assertEqual(verdict_for("new", "low", True, False), "discard")

    def test_low_but_job_add(self):
        """quality=low 但 is_job=true（招聘页）→ 仍收录。"""
        self.assertEqual(verdict_for("new", "low", True, True), "add")


# ---------- evaluate 主流程 ----------

class TestEvaluateValid(unittest.TestCase):
    def test_mixed_verdicts(self):
        """合法 LLM 输出：add / discard / merge 混合判定。"""
        result = _llm_items(
            {"novelty": "new", "quality": "high", "keep": True, "reason": "新岗位"},
            {"novelty": "new", "quality": "low", "keep": False, "reason": "非招聘"},
            {"novelty": "seen", "quality": "high", "keep": True, "reason": "信息更全"},
        )
        annotated, meta = evaluate(ITEMS, {"https://job1.com/a"}, llm_call=_llm_factory(result))
        self.assertFalse(meta["degraded"])
        self.assertEqual(annotated[0]["_eval"]["verdict"], "add")
        self.assertEqual(annotated[1]["_eval"]["verdict"], "discard")
        self.assertEqual(annotated[2]["_eval"]["verdict"], "merge")

    def test_prompt_and_batch_passed(self):
        calls = []
        result = _llm_items({"novelty": "new", "quality": "high", "keep": True, "reason": "ok"})
        evaluate(ITEMS[:1], set(), llm_call=_llm_factory(result, calls=calls))
        self.assertEqual(calls[0][0], EVALUATE_SYSTEM)      # system 正确
        self.assertIn("https://job1.com/a", calls[0][1])    # user 为批量输入


class TestEvaluateDegraded(unittest.TestCase):
    def test_llm_missing_item_filled_by_rule(self):
        """LLM 只评第 0 条 → 其余规则补（不视为降级）。"""
        result = _llm_items({"novelty": "new", "quality": "high", "keep": True, "reason": "ok"})
        annotated, meta = evaluate(ITEMS, set(), llm_call=_llm_factory(result))
        self.assertFalse(meta["degraded"])                  # 部分缺失走规则补，非降级
        self.assertEqual(annotated[0]["_eval"]["verdict"], "add")
        self.assertEqual(annotated[1]["_eval"]["verdict"], "discard")  # 规则补：is_job=false
        # 规则补时 existing_urls 为空集 → item2 novelty=new、is_job=true → add
        self.assertEqual(annotated[2]["_eval"]["novelty"], "new")
        self.assertEqual(annotated[2]["_eval"]["verdict"], "add")

    def test_llm_raises_full_fallback(self):
        annotated, meta = evaluate(ITEMS, {"https://job1.com/a"},
                                   llm_call=_llm_factory(error=RuntimeError("超时")))
        self.assertTrue(meta["degraded"])
        self.assertFalse(meta["llm_called"])
        # 规则降级：item0 URL 已收录 → seen → merge；item1 非招聘 → discard；item2 重复 URL → seen → merge
        self.assertEqual(annotated[0]["_eval"]["verdict"], "merge")
        self.assertEqual(annotated[1]["_eval"]["verdict"], "discard")
        self.assertEqual(annotated[2]["_eval"]["verdict"], "merge")

    def test_invalid_novelty_full_fallback(self):
        result = {"items": [{"index": 0, "novelty": "weird", "quality": "high", "keep": True}]}
        annotated, meta = evaluate(ITEMS, set(), llm_call=_llm_factory(result))
        self.assertTrue(meta["degraded"])
        self.assertEqual(annotated[0]["_eval"]["novelty"], "new")  # 全量规则降级

    def test_not_dict(self):
        annotated, meta = evaluate(ITEMS, set(), llm_call=_llm_factory("nope"))
        self.assertTrue(meta["degraded"])

    def test_empty_items(self):
        annotated, meta = evaluate([], set(), llm_call=_llm_factory({}))
        self.assertEqual(annotated, [])
        self.assertFalse(meta["degraded"])


# ---------- 规则降级评估器 ----------

class TestRuleFallback(unittest.TestCase):
    def test_new_and_seen(self):
        out = rule_fallback_evaluation(ITEMS, {"https://job1.com/a"})
        self.assertEqual(out[0]["_eval"]["novelty"], "seen")     # 已收录 URL
        self.assertEqual(out[0]["_eval"]["verdict"], "merge")
        self.assertEqual(out[1]["_eval"]["verdict"], "discard")  # 非招聘
        self.assertEqual(out[2]["_eval"]["novelty"], "seen")

    def test_empty_existing_urls(self):
        out = rule_fallback_evaluation(ITEMS[:1], set())
        self.assertEqual(out[0]["_eval"]["novelty"], "new")
        self.assertEqual(out[0]["_eval"]["verdict"], "add")


if __name__ == "__main__":
    unittest.main(verbosity=2)
