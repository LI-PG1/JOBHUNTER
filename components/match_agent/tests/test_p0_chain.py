"""P0 线性链端到端测试：build_match_chain() 契约、过滤规则、版本透传、Key 校验。

运行：python -m tests（match_agent 目录下，自动发现本文件）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # components/

from match_agent import build_match_chain  # noqa: E402
from match_agent.llm import LLMKeyError, resolve_llm  # noqa: E402
from match_agent.tools.fake_backend import FakeSearchBackend  # noqa: E402

INPUT = {
    "profile": {
        "background": "硕士在读，AI 方向",
        "skills": ["Python", "深度学习", "PyTorch"],
        "experience": [{"name": "推理优化项目", "desc": "vLLM 部署与优化"}],
        "preference": {"city": "深圳", "direction": "AI"},
        "degree": "硕士",
    },
    "resume": {"version_id": "line-aiinfra-v2", "title": "AI应用开发工程师"},
    "target_jobs": [
        {"title": "AI应用开发工程师", "company": "示例科技",
         "jd": "Python 深度学习 大模型 推理优化"},
    ],
    "resumeVer": "line-aiinfra-v2",
}


class TestP0Chain(unittest.TestCase):
    def test_mock_e2e_contract(self):
        """mock 链端到端：输出契约结构 + 版本透传 + 无错误。"""
        out = build_match_chain(backend="mock").invoke(dict(INPUT))
        self.assertIn("match_results", out)
        self.assertIn("llm_verdicts", out)
        self.assertEqual(out["errors"], [])
        self.assertGreaterEqual(len(out["match_results"]), 1)
        for item in out["match_results"]:
            self.assertEqual(item["resumeVer"], "line-aiinfra-v2")  # Q10d 版本透传
            self.assertIn("job_id", item)
            self.assertIn("score", item)
            self.assertIn("reasons", item)

    def test_accept_gap_ranking(self):
        """高分岗位 accepted 且排序靠前；gap 岗位保留。"""
        out = build_match_chain(backend="mock").invoke(dict(INPUT))
        results = out["match_results"]
        scores = [r["score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))  # final_score 降序
        self.assertGreater(scores[0], 80)                       # 深度学习算法实习生→accepted
        top = results[0]
        self.assertIn("深度学习", top["title"])

    def test_filters_exclude_stale_and_nonjob(self):
        """超时效岗位与非岗位条目被排除。"""
        out = build_match_chain(backend="mock").invoke(dict(INPUT))
        titles = [r["title"] for r in out["match_results"]]
        self.assertNotIn("已过期岗位", titles)
        self.assertNotIn("技术博客文章", titles)

    def test_gap_summary_export(self):
        """Q7 契约：match_agent 导出结构化差距摘要（missing/reject/search_health）。"""
        out = build_match_chain(backend="mock").invoke(dict(INPUT))
        gs = out["gap_summary"]
        self.assertIn("search_health", gs)
        self.assertGreaterEqual(gs["search_health"]["accepted"], 1)
        self.assertGreaterEqual(gs["search_health"]["excluded"], 1)   # 超时效+非岗位
        self.assertGreaterEqual(len(gs["reject_reasons"]), 1)
        self.assertIn("PyTorch", [m["skill"] for m in gs["missing_skills"]])  # gap 岗位缺口

    def test_custom_search_chain_injection(self):
        """注入自定义搜索链（测试替身）。"""
        class CustomChain:
            def search(self, query, num=8, channel=None, preferred=None):
                from match_agent.tools.fake_backend import fake_response
                return fake_response(query)

        out = build_match_chain(backend="mock", search_chain=CustomChain()).invoke(dict(INPUT))
        self.assertGreaterEqual(len(out["match_results"]), 1)

    def test_llm_key_required_d13(self):
        """D13：real 模式缺 Key → LLMKeyError（不提供无 Key 降级）。"""
        with self.assertRaises(LLMKeyError):
            resolve_llm(backend="real", api_key="", model="deepseek-v4-flash")

    def test_llm_mock_ok(self):
        """mock 模式无需 Key，chat_json 可调用。"""
        client = resolve_llm(backend="mock")
        obj, meta = client.chat_json("s", "u")
        self.assertTrue(obj.get("__mock__"))
        self.assertEqual(meta["backend"], "mock")


if __name__ == "__main__":
    unittest.main()
