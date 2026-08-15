"""brake_check 五闸门的测试：各闸门触发 / 不触发 / 优先级 / 结果结构。

运行：python -m tests（match_agent 目录下，自动发现并纳入主测试）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nodes"))

from brake import BrakeResult, brake_check  # noqa: E402


def _base(**over) -> dict:
    """默认参数（均不触发任何闸门）。"""
    params = dict(
        rounds=1, max_rounds=10, min_rounds=3,
        no_new_rounds=0, budget_left=10,
        executed=set(), queries=["q1", "q2"], degraded_decide=0,
    )
    params.update(over)
    return params


class TestBrakeCheck(unittest.TestCase):
    def test_no_trigger_continue(self):
        """全部闸门未命中 → continue。"""
        r = brake_check(**_base())
        self.assertFalse(r.should_converge)
        self.assertEqual(r.reason, "")

    def test_g1_round_limit(self):
        r = brake_check(**_base(rounds=10, max_rounds=10))
        self.assertTrue(r.should_converge)
        self.assertIn("G1", r.reason)

    def test_g2_no_new_converge(self):
        r = brake_check(**_base(no_new_rounds=2, rounds=3, min_rounds=3))
        self.assertTrue(r.should_converge)
        self.assertIn("G2", r.reason)

    def test_g2_below_min_rounds_continue(self):
        """连续无新增但未达最小轮数 → 不收敛。"""
        r = brake_check(**_base(no_new_rounds=2, rounds=2, min_rounds=3))
        self.assertFalse(r.should_converge)

    def test_g3_budget(self):
        r = brake_check(**_base(budget_left=0))
        self.assertTrue(r.should_converge)
        self.assertIn("G3", r.reason)

    def test_g4_all_executed(self):
        r = brake_check(**_base(executed={"q1", "q2"}))
        self.assertTrue(r.should_converge)
        self.assertIn("G4", r.reason)

    def test_g4_pending_continue(self):
        """仍有待执行 query → 不收敛。"""
        r = brake_check(**_base(executed={"q1"}))
        self.assertFalse(r.should_converge)

    def test_g4_empty_queries(self):
        """query 列表为空（无待执行）→ 收敛。"""
        r = brake_check(**_base(queries=[]))
        self.assertTrue(r.should_converge)
        self.assertIn("G4", r.reason)

    def test_g5_degraded_three(self):
        r = brake_check(**_base(degraded_decide=3))
        self.assertTrue(r.should_converge)
        self.assertIn("G5", r.reason)

    def test_g5_below_three_continue(self):
        r = brake_check(**_base(degraded_decide=2))
        self.assertFalse(r.should_converge)

    def test_priority_g1_first(self):
        """多闸门同时满足 → 返回 G1。"""
        r = brake_check(**_base(rounds=10, max_rounds=10, budget_left=0, degraded_decide=5))
        self.assertIn("G1", r.reason)

    def test_priority_g2_after_g1(self):
        """G1 不满足但 G2/G5 满足 → 返回 G2。"""
        r = brake_check(**_base(no_new_rounds=2, rounds=4, min_rounds=3, degraded_decide=5))
        self.assertIn("G2", r.reason)

    def test_result_dataclass(self):
        r = brake_check(**_base())
        self.assertIsInstance(r, BrakeResult)
        self.assertIsInstance(r.should_converge, bool)
        self.assertIsInstance(r.reason, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
