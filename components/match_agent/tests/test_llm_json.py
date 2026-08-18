"""LLM 返回 JSON 健壮解析测试（safe_json_loads）。

覆盖：围栏剥离 / 平衡区间截取 / 尾逗号 / 单引号 / 顶层数组归一化 /
完全不可解析（返回 None 供降级）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import diagnose_json, safe_json_loads  # noqa: E402


class TestSafeJsonLoads(unittest.TestCase):

    def test_plain_json(self):
        obj, repaired = safe_json_loads('{"items": [{"gap": "a"}]}')
        self.assertEqual(obj["items"][0]["gap"], "a")

    def test_fenced_json(self):
        text = "好的，这是结果：\n```json\n{\"items\": [{\"gap\": \"x\"}]}\n```\n希望有帮助"
        obj, _ = safe_json_loads(text)
        self.assertEqual(obj["items"][0]["gap"], "x")

    def test_prefix_surround_text(self):
        text = "以下是分析结果：\n{\"items\": [{\"gap\": \"y\"}]}\n（完）"
        obj, _ = safe_json_loads(text)
        self.assertEqual(obj["items"][0]["gap"], "y")

    def test_trailing_commas(self):
        text = '{"items": [{"gap": "z", "priority": "high",},],}'
        obj, repaired = safe_json_loads(text)
        self.assertTrue(repaired)
        self.assertEqual(obj["items"][0]["gap"], "z")

    def test_single_quotes(self):
        text = "{'items': [{'gap': '单引号'}]}"
        obj, _ = safe_json_loads(text)
        self.assertEqual(obj["items"][0]["gap"], "单引号")

    def test_top_level_array_normalized(self):
        text = '[{"gap": "arr", "suggestion": "s"}]'
        obj, _ = safe_json_loads(text)
        self.assertIn("items", obj)          # 数组 → {"items": [...]}
        self.assertEqual(obj["items"][0]["gap"], "arr")

    def test_unparseable_returns_none(self):
        obj, _ = safe_json_loads("完全不是 JSON 的内容")
        self.assertIsNone(obj)

    def test_empty_input(self):
        self.assertIsNone(safe_json_loads("")[0])
        self.assertIsNone(safe_json_loads(None)[0])

    def test_truncated_outer_recovered(self):
        # 外层右括号被截断，但内层 items 数组完整 → 部分恢复（优于全丢）
        obj, _ = safe_json_loads('{"items": [{"gap": "t"}]')
        self.assertEqual(obj["items"][0]["gap"], "t")

    def test_truncated_inner_unparseable(self):
        # 内层也截断（字符串未闭合）→ 无法解析 → None 供降级
        obj, _ = safe_json_loads('{"items": [{"gap": "t"')
        self.assertIsNone(obj)

    # ---- diagnose_json：失败原因分类（供 N7 日志统计定位） ----

    def test_diagnose_truncated(self):
        issues = diagnose_json('{"items": [{"gap": "t"')
        self.assertTrue(any("括号不平衡" in i for i in issues))

    def test_diagnose_no_json(self):
        issues = diagnose_json("完全不是 JSON 的内容")
        self.assertTrue(any("无 JSON 结构" in i for i in issues))

    def test_diagnose_single_quotes_and_truncated(self):
        issues = diagnose_json("{'gap': 'x'")
        self.assertTrue(any("单引号" in i for i in issues))
        self.assertTrue(any("括号不平衡" in i for i in issues))

    def test_diagnose_trailing_commas(self):
        issues = diagnose_json('{"a": 1,}')
        self.assertTrue(any("尾逗号" in i for i in issues))

    def test_diagnose_empty(self):
        self.assertEqual(diagnose_json(""), ["空输入/非字符串"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
