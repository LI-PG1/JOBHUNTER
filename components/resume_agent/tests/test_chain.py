"""resume_agent P0 链测试：build_resume_chain() 端到端、契约、降级隔离、数量约束。

运行：python -m tests（resume_agent 目录下，自动发现本文件）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # components/

from resume_agent import build_resume_chain  # noqa: E402
from resume_agent.mock_provider import MockLLMProvider  # noqa: E402

RESUME = {
    "id": "t1", "identity": "intern", "pageOption": "one-page",
    "basicInfo": {"name": "测试用户", "age": 24, "email": "a@b.com", "phone": "13800000000"},
    "education": [{"school": "某大学", "major": "计算机科学与技术", "degree": "硕士",
                   "startMonth": "2024.09", "endMonth": "2026.06"}],
    "skill": [
        {"name": "Python", "level": "熟练", "category": "专业技能"},
        {"name": "LangChain", "level": "熟练", "category": "工具与框架", "skillExtend": True},
    ],
    "internship": [{"company": "示例科技", "position": "算法实习生",
                    "startMonth": "2025.06", "endMonth": "2025.09",
                    "overview": "负责检索系统开发",
                    "duties": [{"text": "实现向量检索流程", "criticality": "high"}]}],
    "project": [{"name": "RAG 检索系统", "role": "核心开发",
                 "techStack": ["Python", "LangChain"],
                 "startMonth": "2025.01", "endMonth": "2025.04",
                 "items": [{"text": "实现向量检索与重排", "criticality": "high"}],
                 "source": "user-input", "aiFlag": False}],
    "generation": {"deepSearch": False},
    "contentPlan": {"projectCount": 2},
    "jobs": [{"id": "j1", "title": "AI应用开发工程师",
              "jdText": "负责大模型应用与 RAG 系统开发，熟悉 Python、LangChain、向量检索",
              "domainTags": []}],
}


class TestResumeChain(unittest.IsolatedAsyncioTestCase):
    async def test_e2e_chain(self):
        """mock provider 端到端：html 渲染、板块产出、简历回写。"""
        out = await build_resume_chain(provider=MockLLMProvider()).ainvoke(
            {"direction": "大模型应用开发", "resume": dict(RESUME)})
        blocks = out["blocks"]
        self.assertIn("summary", blocks)
        self.assertIn("projects", blocks)
        self.assertLessEqual(len(blocks["summary"].get("sentences") or []), 2)  # 数量约束
        self.assertTrue(out["html"].strip())                        # 模板装配产出
        self.assertIn("summary", out["resume"])                     # 回写
        self.assertIn("project", out["resume"])
        self.assertEqual(out["resume"]["contentPlan"]["bulletCountPerProject"], 4)  # 一页恒 4 条 STAR

    async def test_contract(self):
        """输出契约：factsheet / review_results / errors。"""
        out = await build_resume_chain(provider=MockLLMProvider()).ainvoke(
            {"direction": "大模型应用开发", "resume": dict(RESUME)})
        self.assertIn("factsheet", out)
        self.assertEqual(out["factsheet"]["direction"], "大模型应用开发")
        # P3：review_results 已填充（block → verdict/rounds/rewritten/blockerCount）
        rr = out["review_results"]
        self.assertTrue(rr)
        self.assertIn("projects", rr)
        for r in rr.values():
            self.assertIn("verdict", r)
            self.assertIn("rounds", r)
            self.assertIn("rewritten", r)
            self.assertIn("blockerCount", r)
        self.assertEqual(out["errors"], [])

    async def test_degrade_isolation(self):
        """projects 块 LLM 失败 → degraded 标记，其余块正常，链不抛。"""
        out = await build_resume_chain(
            provider=MockLLMProvider(fail_on="项目经历撰写师")).ainvoke(
            {"direction": "大模型应用开发", "resume": dict(RESUME)})
        self.assertTrue(out["blocks"]["projects"].get("degraded"))
        self.assertFalse(out["blocks"]["summary"].get("degraded"))
        self.assertTrue(out["html"].strip())                        # 整单继续

    async def test_skill_extend(self):
        """skillExtend=true → skill_extend 产出并入 skill。"""
        out = await build_resume_chain(provider=MockLLMProvider()).ainvoke(
            {"direction": "大模型应用开发", "resume": dict(RESUME)})
        names = {s["name"] for s in out["resume"]["skill"]}
        self.assertIn("Milvus", names)                              # 拓展技能并入
        self.assertGreaterEqual(len(out["blocks"].get("skill_extend", {}).get("skills") or []), 1)

    async def test_edited_lock_preserved(self):
        """用户已编辑项（edited=true）不被重写覆盖。"""
        resume = dict(RESUME)
        resume["summary"] = [{"text": "用户手动写的自我评价（锁定）", "criticality": "critical", "edited": True}]
        out = await build_resume_chain(provider=MockLLMProvider()).ainvoke(
            {"direction": "大模型应用开发", "resume": resume})
        texts = [s.get("text") for s in out["resume"].get("summary") or []]
        self.assertIn("用户手动写的自我评价（锁定）", texts)

    async def test_review_rewrite_triggered(self):
        """差板块（要点条数不足 STAR 四段）→ 规则 blocker → 带意见重写真实触发。

        mock provider 的项目输出恒为 3 条要点（< 4），check_star_chain 判 blocker；
        review_block 调原生成函数携带 review_feedback 重写，mock 重写结果不改善 →
        回退最优版本并给出 accept_with_issues（rounds=1, rewritten=True）。
        """
        out = await build_resume_chain(provider=MockLLMProvider()).ainvoke(
            {"direction": "大模型应用开发", "resume": dict(RESUME)})
        rp = out["review_results"]["projects"]
        self.assertEqual(rp["block"], "projects")
        self.assertIn(rp["verdict"], ("pass", "accept_with_issues"))
        self.assertEqual(rp["rounds"], 1)                 # 重写 1 轮后复审未改善 → 停止
        self.assertTrue(rp["rewritten"])                  # blocker 真实触发了重写
        self.assertGreater(rp["blockerCount"], 0)         # 规则 blocker 存在（条数 < 4）
        self.assertIsInstance(out["blocks"]["projects"], dict)  # 链继续，产出结构完整


if __name__ == "__main__":
    unittest.main()
