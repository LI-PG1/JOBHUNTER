"""resume_agent 四阶段链（P3：prepare/generate/review/build Runnable 化）。

对齐架构 §3.5：引入 langchain（LCEL），四阶段链式化（review 为 P3 接入子图）。
- 进程内内存态：无 storage/task 持久化（与大脑集成形态一致，Q9 同款）。
- 引擎依赖复制自 JL-Agent 工程（lib/app 包，导入路径不变）。
- review 阶段：规则审核 → blocker 带意见重写 → 复审（§3.2 子图，进程内无事件/进度）。
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

LIB = Path(__file__).resolve().parent / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from app.config import Config, load_config  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.core.providers import LLMProvider  # noqa: E402
from app.core.rules import RulesLoader  # noqa: E402
from app.engine.analysis import JDAnalyzer  # noqa: E402
from app.engine.assembly import Assembler  # noqa: E402
from app.engine.blocks import BLOCK_GENERATORS, LAYER1, LAYER2  # noqa: E402
from app.engine.blocks.base import GenContext  # noqa: E402
from app.engine.blocks.projects import bullet_limit  # noqa: E402
from app.engine.budget import BudgetTracker  # noqa: E402
from app.engine.cache import GenCache  # noqa: E402
from app.engine.review import REVIEWABLE_BLOCKS, review_block  # noqa: E402
from app.schemas import Job, Resume  # noqa: E402

from resume_agent.state import ResumeState  # noqa: E402


class ResumeRunner:
    """进程内三阶段执行器（组件版：无 FastAPI/storage 依赖）。"""

    def __init__(self, provider: Any | None = None, config: Config | None = None):
        self.config = config or load_config()
        # lib 依赖路径修正：config 的 paths 为相对值，组件内一律指到 lib/ 绝对路径
        self.config.paths.rules_dir = str(LIB / "rules")
        self.config.paths.templates_dir = str(LIB / "templates")
        self.rules = RulesLoader(self.config.paths.rules_dir)
        self.rules.load_all()                     # 规则缺失/非法 → 启动即报错（fail fast）
        self.provider = provider or LLMProvider(self.config)
        self.analyzer = JDAnalyzer(self.provider, self.rules)
        self._fs_cache: dict[str, dict[str, Any]] = {}
        self._data_dir = tempfile.mkdtemp(prefix="resume_agent_")
        self.cache = GenCache(self._data_dir)
        self.budget = BudgetTracker(self._data_dir)

    # ---------------------------------------------------------------- prepare（analyzing）

    async def prepare(self, state: ResumeState) -> ResumeState:
        """简历+JD → 共享事实表 factsheet → GenContext。增量更新：factsheet/_ctx。"""
        resume = state.get("resume") or {}
        jobs = state.get("jobs") or resume.get("jobs") or []
        page_option = resume.get("pageOption", "one-page")
        identity = resume.get("identity", "intern")
        gen = resume.get("generation") or {}
        deep_search = bool(gen.get("deepSearch"))          # P1 联网检索接入
        skill_extend_enabled = any(s.get("skillExtend") for s in (resume.get("skill") or []))
        project_count = (resume.get("contentPlan") or {}).get("projectCount") or 0
        version = (self.rules.jobs_rules() or {}).get("version", "1.0")

        key = GenCache.jd_key(jobs, page_option, identity, version)
        factsheet = self._fs_cache.get(key)                 # 进程内缓存（原文件缓存替代）
        if not factsheet:
            fs = await self.analyzer.analyze(
                [Job(**j) for j in jobs], Resume(**resume), page_option, deep_search)
            factsheet = fs.model_dump(mode="json", by_alias=True)
            self._fs_cache[key] = factsheet

        ctx = GenContext(
            task_id="resume_agent", resume_id="resume_agent",
            resume=resume, jobs=jobs, factsheet=factsheet,
            page_option=page_option, project_count=project_count,
            skill_extend_enabled=skill_extend_enabled,
            industry_rules=self._match_industry(factsheet),
            provider=self.provider, rules=self.rules, cache=self.cache,
            analyzer=self.analyzer, budget=self.budget, config=self.config,
        )
        return {**state, "factsheet": factsheet, "_ctx": ctx}

    def _match_industry(self, factsheet: dict) -> dict:
        direction = factsheet.get("direction", "")
        best, best_score = {}, 0
        for payload in self.rules.industries().values():
            score = sum(1 for kw in payload.get("keywords", []) if kw.lower() in direction.lower())
            if score > best_score:
                best, best_score = payload, score
        return best

    # ---------------------------------------------------------------- generate（generating）

    async def generate(self, state: ResumeState) -> ResumeState:
        """LAYER1/LAYER2 并行执行全部板块（原 dag._generate + _run_block）。"""
        ctx = state["_ctx"]
        for layer in (LAYER1, LAYER2):
            await asyncio.gather(*[self._run_block(ctx, b) for b in layer])
        return {**state, "blocks": dict(ctx.blocks)}

    async def _run_block(self, ctx: GenContext, name: str) -> None:
        """单块执行 + 失败降级（原 dag.py:236-243，模块级失败隔离 §5.6）。"""
        try:
            output = await BLOCK_GENERATORS[name](ctx)
        except AppError as exc:
            output = {"degraded": True, "error": exc.message}
        except Exception as exc:  # noqa: BLE001
            output = {"degraded": True, "error": str(exc)}
        ctx.blocks[name] = output
        self.budget.record_estimated(name, output)

    # ---------------------------------------------------------------- review（reviewing）

    async def review(self, state: ResumeState) -> ResumeState:
        """P3 子图：规则审核 → blocker 带意见重写 → 复审（进程内，无事件/进度）。

        直接复用 lib 的 review_block（规则审核零 LLM；重写走原板块生成函数并携带
        上轮审核意见；复审未改善自动回退最优版本）。config.review.enabled=false 时跳过。
        """
        ctx = state["_ctx"]
        review_cfg = getattr(ctx.config, "review", None)
        if review_cfg is not None and not review_cfg.enabled:
            return {**state, "review_results": {}, "rounds": {}}
        blocks = [b for b in REVIEWABLE_BLOCKS if ctx.blocks.get(b)]
        results = await asyncio.gather(*[review_block(ctx, b) for b in blocks]) if blocks else []
        ctx.review_summary = {"results": results}
        return {
            **state,
            "review_results": {r["block"]: r for r in results},
            "rounds": {r["block"]: r["rounds"] for r in results},
            "blocks": dict(ctx.blocks),   # 重写已替换 ctx.blocks 中的板块输出
        }

    # ---------------------------------------------------------------- build（building）

    async def build(self, state: ResumeState) -> ResumeState:
        """板块结果回写简历 + 模板装配 → html/config（原 dag._build 去 storage 化）。"""
        ctx = state["_ctx"]
        blocks = ctx.blocks
        resume = dict(ctx.resume)

        if blocks.get("summary"):
            resume["summary"] = blocks["summary"].get("sentences") or []
        if blocks.get("internship"):
            resume["internship"] = blocks["internship"].get("items") or resume.get("internship") or []
        if blocks.get("projects"):
            resume["project"] = blocks["projects"].get("projects") or resume.get("project") or []
        if blocks.get("skills"):
            skills = blocks["skills"].get("skills") or []
            extend = blocks.get("skill_extend", {}).get("skills") or []
            names = {s.get("name", "") for s in skills}
            skills = skills + [s for s in extend if s.get("name") not in names]
            resume["skill"] = skills
        if blocks.get("honor") and not blocks["honor"].get("skipped"):
            resume["honor"] = blocks["honor"].get("items") or []

        resume["contentPlan"] = {
            **dict(resume.get("contentPlan") or {}),
            "detailLevel": "标准",
            "bulletCountPerProject": bullet_limit(
                ctx.page_option,
                len((blocks.get("projects") or {}).get("projects") or [])),
        }
        gen = dict(resume.get("generation") or {})
        gen["direction"] = ctx.factsheet.get("direction", "")
        resume["generation"] = gen

        # 模板装配（原 dag._build：模板缺失为致命 E_TEMPLATE）
        assembler = Assembler(self.config.paths.templates_dir, None)
        html, assembly_config = assembler.render(
            resume, blocks,
            density=resume.get("density", "normal"),
            watermark_mode=gen.get("watermarkMode", "practice"),
        )
        return {**state, "resume": resume, "html": html, "assembly_config": assembly_config}
