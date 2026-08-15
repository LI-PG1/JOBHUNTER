"""decide 决策器的 mock 测试：提示词内容 / schema 校验 / converge 护栏 / 规则降级逻辑。

运行：python -m tests（match_agent 目录下，自动发现本文件）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nodes"))

from decide import (  # noqa: E402
    ACTIONS, CHANNELS, DECIDE_SYSTEM,
    build_user_context, decide, rule_fallback_decision, validate_decision,
)

CARD = {
    "city": "深圳",
    "skill_line": "inference",
    "education": "硕士",
    "skills": [{"name": "vLLM"}, {"name": "PyTorch"}],
}
ROUND_STATS = [
    {"query": "深圳 AI 推理工程师 招聘", "backend": "百度", "found": 8, "new": 3, "kept": 2},
]


def _llm_factory(result=None, error=None, calls=None):
    """构造可注入的 mock llm_call；记录 (system, user) 调用。"""
    def _mock_llm(system, user, provider_id=None, model=None, max_tokens=None):
        if calls is not None:
            calls.append((system, user, provider_id, model, max_tokens))
        if error is not None:
            raise error
        return (result if result is not None else {}), {}
    return _mock_llm


class TestDecideSystem(unittest.TestCase):
    """提示词验证。"""

    def test_prompt_contains_all_actions(self):
        """DECIDE_SYSTEM 必须覆盖全部动作枚举。"""
        for a in ACTIONS:
            self.assertIn(a, DECIDE_SYSTEM, f"提示词缺少动作 {a}")

    def test_prompt_contains_json_schema(self):
        """提示词包含严格 JSON 结构与动作说明。"""
        self.assertIn("action", DECIDE_SYSTEM)
        self.assertIn("params", DECIDE_SYSTEM)
        self.assertIn("reason", DECIDE_SYSTEM)
        self.assertIn("converge", DECIDE_SYSTEM)

    def test_prompt_contains_guardrail(self):
        """提示词向 LLM 声明 converge 护栏。"""
        self.assertIn("最小轮数", DECIDE_SYSTEM)
        self.assertIn("目标收录数", DECIDE_SYSTEM)


class TestBuildUserContext(unittest.TestCase):
    def test_context_contains_key_info(self):
        """user 上下文包含画像/进度/收录缺口/预算。"""
        user = build_user_context(CARD, ROUND_STATS, entries_count=5, target_entries=20,
                                  rounds=2, budget_left=10)
        self.assertIn("深圳", user)
        self.assertIn("inference", user)
        self.assertIn("已收录数", user)
        self.assertIn("目标收录数", user)
        self.assertIn("剩余预算", user)
        self.assertIn("每轮行动统计", user)
        self.assertIn("深圳 AI 推理工程师 招聘", user)


class TestDecideValid(unittest.TestCase):
    """合法决策透传。"""

    def test_valid_rewrite(self):
        calls = []
        result = {"action": "rewrite_query", "params": {"query": "深圳 vLLM 部署 招聘"}, "reason": "换个角度"}
        decision, meta = decide(["q1"], set(), rounds=1, min_rounds=3,
                                entries_count=5, target_entries=20, budget_left=10,
                                card=CARD, llm_call=_llm_factory(result, calls=calls))
        self.assertEqual(decision, result)
        self.assertFalse(meta["degraded"])
        # 调用参数：system=DECIDE_SYSTEM、user 为上下文、max_tokens=800
        self.assertEqual(calls[0][0], DECIDE_SYSTEM)
        self.assertEqual(calls[0][4], 800)

    def test_valid_converge(self):
        result = {"action": "converge", "params": {}, "reason": "已达标"}
        decision, meta = decide(["q1"], {"q1"}, rounds=4, min_rounds=3,
                                entries_count=25, target_entries=20, budget_left=5,
                                card=CARD, llm_call=_llm_factory(result))
        self.assertEqual(decision["action"], "converge")
        self.assertFalse(meta["degraded"])


class TestDecideGuardrail(unittest.TestCase):
    """converge 护栏：不满足即判非法 → 规则降级。"""

    def test_converge_below_min_rounds(self):
        result = {"action": "converge", "params": {}, "reason": "够了"}
        decision, meta = decide(["q1"], set(), rounds=1, min_rounds=3,
                                entries_count=25, target_entries=20, budget_left=5,
                                card=CARD, llm_call=_llm_factory(result))
        self.assertTrue(meta["degraded"])
        self.assertIn("converge 不满足收敛护栏", meta["error"])
        self.assertEqual(decision["action"], "rewrite_query")  # 降级：顺序执行未搜索 query

    def test_converge_below_target_entries(self):
        result = {"action": "converge", "params": {}, "reason": "够了"}
        decision, meta = decide(["q1"], {"q1"}, rounds=4, min_rounds=3,
                                entries_count=3, target_entries=20, budget_left=5,
                                card=CARD, llm_call=_llm_factory(result))
        self.assertTrue(meta["degraded"])
        self.assertEqual(decision["action"], "converge")  # 无未执行 query → 降级收敛


class TestDecideInvalid(unittest.TestCase):
    """非法决策（schema）→ 规则降级。"""

    def test_unknown_action(self):
        result = {"action": "fly", "params": {}, "reason": "乱来"}
        decision, meta = decide(["q1"], set(), rounds=1, min_rounds=3,
                                entries_count=5, target_entries=20, budget_left=10,
                                card=CARD, llm_call=_llm_factory(result))
        self.assertTrue(meta["degraded"])
        self.assertIn("未知 action", meta["error"])
        self.assertEqual(decision["params"]["query"], "q1")

    def test_rewrite_missing_query(self):
        result = {"action": "rewrite_query", "params": {}, "reason": "忘了query"}
        decision, meta = decide(["q1"], set(), rounds=1, min_rounds=3,
                                entries_count=5, target_entries=20, budget_left=10,
                                card=CARD, llm_call=_llm_factory(result))
        self.assertTrue(meta["degraded"])
        self.assertIn("缺少 params.query", meta["error"])

    def test_invalid_channel(self):
        result = {"action": "switch_channel", "params": {"channel": "微信"}, "reason": "换渠道"}
        decision, meta = decide(["q1"], set(), rounds=1, min_rounds=3,
                                entries_count=5, target_entries=20, budget_left=10,
                                card=CARD, llm_call=_llm_factory(result))
        self.assertTrue(meta["degraded"])
        self.assertIn("渠道非法", meta["error"])

    def test_not_a_dict(self):
        decision, meta = decide(["q1"], set(), rounds=1, min_rounds=3,
                                entries_count=5, target_entries=20, budget_left=10,
                                card=CARD, llm_call=_llm_factory(["not", "dict"]))
        self.assertTrue(meta["degraded"])
        self.assertIn("不是 JSON 对象", meta["error"])


class TestDecideLLMFailure(unittest.TestCase):
    """LLM 异常 → 规则降级。"""

    def test_llm_raises(self):
        decision, meta = decide(["q1"], set(), rounds=1, min_rounds=3,
                                entries_count=5, target_entries=20, budget_left=10,
                                card=CARD, llm_call=_llm_factory(error=RuntimeError("超时")))
        self.assertTrue(meta["degraded"])
        self.assertFalse(meta["llm_called"])
        self.assertIn("LLM 调用失败", meta["error"])
        self.assertEqual(decision["action"], "rewrite_query")


class TestRuleFallback(unittest.TestCase):
    """规则降级决策器（机械策略）直接验证。"""

    def test_pending_query_first(self):
        d = rule_fallback_decision(["q1", "q2"], {"q2"}, rounds=2, min_rounds=3)
        self.assertEqual(d["action"], "rewrite_query")
        self.assertEqual(d["params"]["query"], "q1")  # 顺序取第一条未执行

    def test_no_pending_converge(self):
        d = rule_fallback_decision(["q1", "q2"], {"q1", "q2"}, rounds=3, min_rounds=3)
        self.assertEqual(d["action"], "converge")

    def test_empty_queries(self):
        d = rule_fallback_decision([], set(), rounds=1, min_rounds=3)
        self.assertEqual(d["action"], "converge")


class TestValidateDecision(unittest.TestCase):
    def test_channel_enum(self):
        self.assertEqual(set(CHANNELS), {"招聘平台", "官网", "社区"})

    def test_valid_rewrite_pass(self):
        ok, err = validate_decision(
            {"action": "rewrite_query", "params": {"query": "x"}, "reason": ""},
            rounds=1, min_rounds=3, entries_count=0, target_entries=20)
        self.assertTrue(ok)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
