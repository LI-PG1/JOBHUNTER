"""JD 输入边界单测（2026-08-17 规则：岗位名必填 + JD 原文可选但鼓励）。

覆盖 4 个边界场景：
1. jobs 为空列表 → E_PARAM 拦截
2. title 为纯空白（"  "）→ E_PARAM 拦截（strip 后为空，any() 旧逻辑会漏检）
3. 多套 JD 混合 title 空白 → E_PARAM 拦截，且报错指明第几套
4. jd_text 为纯空白 / None / 空串 → 不抛错，prompt 触发「无 JD 原文」降级标注
   （旧逻辑 `j.get('jdText') or ...` 对纯空白串短路失效，会把空白当 JD 传 LLM）

运行：python -m tests（resume_agent 目录下，自动发现本文件）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))           # components/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))   # resume_agent/lib

from app.core.errors import AppError, E_PARAM  # noqa: E402
from app.core.rules import RulesLoader  # noqa: E402
from app.engine.analysis import JDAnalyzer  # noqa: E402
from app.engine.prompts import jd_analysis_messages  # noqa: E402
from app.schemas import Job, Resume  # noqa: E402

from resume_agent.mock_provider import MockLLMProvider  # noqa: E402

LIB = Path(__file__).resolve().parents[1] / "lib"

RESUME = {
    "id": "t-boundary", "identity": "intern", "pageOption": "one-page",
    "basicInfo": {"name": "测试用户", "age": 24, "email": "a@b.com", "phone": "13800000000"},
    "education": [{"school": "某大学", "major": "计算机科学与技术", "degree": "硕士",
                   "startMonth": "2024.09", "endMonth": "2026.06"}],
    "skill": [{"name": "Python", "level": "熟练", "category": "专业技能"}],
    "internship": [],
    "project": [],
    "jobs": [],
}


def make_analyzer() -> JDAnalyzer:
    rules = RulesLoader(str(LIB / "rules"))
    rules.load_all()
    return JDAnalyzer(MockLLMProvider(), rules)


class TestJdBoundary(unittest.IsolatedAsyncioTestCase):
    # ------------------------------------------------------------ 场景 1：jobs 为空

    async def test_analyze_empty_jobs(self):
        """jobs=[] → E_PARAM（"请至少填写 1 套目标岗位 JD"）。"""
        analyzer = make_analyzer()
        with self.assertRaises(AppError) as ctx:
            await analyzer.analyze([], Resume(**RESUME))
        self.assertEqual(ctx.exception.code, E_PARAM)
        self.assertIn("至少填写 1 套", str(ctx.exception))

    # ------------------------------------------------------------ 场景 2：title 纯空白

    async def test_analyze_blank_title(self):
        """title="  "（纯空白）→ E_PARAM 拦截（strip 后为空）。"""
        analyzer = make_analyzer()
        jobs = [Job(title="  ", jd_text=None)]
        with self.assertRaises(AppError) as ctx:
            await analyzer.analyze(jobs, Resume(**RESUME))
        self.assertEqual(ctx.exception.code, E_PARAM)
        self.assertIn("岗位名称不能为空", str(ctx.exception))

    # ------------------------------------------------------------ 场景 3：多套混合空白 title

    async def test_analyze_mixed_blank_title_reports_index(self):
        """多套 JD 中第 2 套 title 空白 → E_PARAM 且指明第 2 套。"""
        analyzer = make_analyzer()
        jobs = [
            Job(title="AI 应用开发工程师", jd_text="负责大模型应用开发"),
            Job(title="   ", jd_text="负责推理部署"),
            Job(title="AI Infra 工程师", jd_text="负责推理优化"),
        ]
        with self.assertRaises(AppError) as ctx:
            await analyzer.analyze(jobs, Resume(**RESUME))
        self.assertEqual(ctx.exception.code, E_PARAM)
        self.assertIn("第 2 套", str(ctx.exception))

    async def test_analyze_mixed_blank_title_ok_when_none_blank(self):
        """对照：全部 title 非空白（含首尾空格）→ 正常通过，不被误伤。"""
        analyzer = make_analyzer()
        jobs = [
            Job(title="  AI 应用开发工程师  ", jd_text="负责大模型应用开发"),
            Job(title="AI Infra 工程师", jd_text=None),   # JD 缺省也允许
        ]
        fs = await analyzer.analyze(jobs, Resume(**RESUME))
        self.assertTrue(fs.direction)                      # mock 返回 direction
        self.assertEqual(fs.core_skills, ["Python", "LangChain", "向量检索"])

    # ------------------------------------------------------------ 场景 4：jd_text 空白/None/空串 → 降级标注

    def test_jd_analysis_messages_blank_jd_text(self):
        """jd_text 纯空白 → prompt 标注「无 JD 原文，按岗位名称推断」，不把空白当 JD。"""
        jobs = [{"title": "AI 工程师", "jdText": "   ", "domainTags": []}]
        msgs = jd_analysis_messages(jobs, {"project_types": [], "metric_style": "", "jobs": {}}, {})
        user = msgs[1]["content"]
        self.assertIn("岗位：AI 工程师", user)
        self.assertIn("无 JD 原文，按岗位名称推断", user)
        self.assertNotIn("JD：   ", user)

    def test_jd_analysis_messages_none_jd_text(self):
        """jd_text=None → prompt 同样触发降级标注。"""
        jobs = [{"title": "AI 工程师", "jdText": None, "domainTags": []}]
        msgs = jd_analysis_messages(jobs, {"project_types": [], "metric_style": "", "jobs": {}}, {})
        user = msgs[1]["content"]
        self.assertIn("无 JD 原文，按岗位名称推断", user)

    def test_jd_analysis_messages_empty_string_jd_text(self):
        """jd_text=""（前端 trim 后空值）→ prompt 触发降级标注。"""
        jobs = [{"title": "AI 工程师", "jdText": "", "domainTags": []}]
        msgs = jd_analysis_messages(jobs, {"project_types": [], "metric_style": "", "jobs": {}}, {})
        user = msgs[1]["content"]
        self.assertIn("无 JD 原文，按岗位名称推断", user)

    def test_jd_analysis_messages_real_jd_preserved(self):
        """对照：jd_text 有真实内容 → 原样保留，不误标降级。"""
        jd = "负责大模型应用与 RAG 系统开发，熟悉 Python、LangChain"
        jobs = [{"title": "AI 工程师", "jdText": jd, "domainTags": []}]
        msgs = jd_analysis_messages(jobs, {"project_types": [], "metric_style": "", "jobs": {}}, {})
        user = msgs[1]["content"]
        self.assertIn(jd, user)
        self.assertNotIn("无 JD 原文", user)


if __name__ == "__main__":
    unittest.main()
