"""生成引擎调度（契约 §5.1 分层并行 DAG / §4.3 状态机 / §4.4 SSE 进度）。

运行流：
  pending → analyzing（JD 分析缓存复用 + 联网搜索 + 共享事实表）
         → generating（第一层并行：summary/education/internship/skills/honor；
                       第二层依赖 factsheet：projects/skill_extend）
         → building（板块结果装配回写简历）→ done

- 进度：板块权重（BLOCK_WEIGHTS）按「本次实际相关板块」归一化，0→1 单调递增。
- 失败隔离（§5.6）：单板块失败重试 1 次后降级输出，整单继续；仅致命错误（事实表/模板）置 failed。
- 事件：全部持久化到 task.events，SSE 断线重连可回放（§4.4）。
"""
import asyncio

from ..core.errors import AppError, E_BLOCK_FAIL, E_SEARCH
from ..core.providers import LLMProvider
from ..schemas import BLOCK_WEIGHTS, Job, Resume
from .analysis import JDAnalyzer
from .assembly import Assembler
from .blocks import BLOCK_GENERATORS, LAYER1, LAYER2
from .blocks.base import GenContext
from .blocks.projects import bullet_limit
from .budget import BudgetTracker
from .cache import GenCache

# 规则块（不占进度权重，但需执行）：荣誉
ZERO_WEIGHT_BLOCKS = {"honor"}

STAGES = ["analyzing", "generating", "building"]
TERMINAL_EVENTS = {"task.done", "task.failed", "task.canceled"}


def build_runner(app) -> "GenerationRunner":
    """从 FastAPI app.state 组装 Runner（路由层调用）。"""
    provider = LLMProvider(app.state.config, app.state.storage)
    return GenerationRunner(
        storage=app.state.storage,
        rules=app.state.rules,
        config=app.state.config,
        provider=provider,
        analyzer=JDAnalyzer(provider, app.state.rules),
        search_client=app.state.search_client,
        cache=app.state.gen_cache,
        budget=BudgetTracker(app.state.config.paths.data_dir),
        now=app.state.now,
    )


class GenerationRunner:
    """单任务串行调度器（无状态，可复用；每次 run 独立上下文）。"""

    def __init__(self, *, storage, rules, config, provider, analyzer, search_client,
                 cache: GenCache, budget: BudgetTracker, now):
        self.storage = storage
        self.rules = rules
        self.config = config
        self.provider = provider
        self.analyzer = analyzer
        self.search_client = search_client
        self.cache = cache
        self.budget = budget
        self.now = now

    # ------------------------------------------------------------ 入口

    async def run(self, task_id: str) -> None:
        """执行任务全流程；任何异常收敛为 task.failed（终态幂等）。"""
        try:
            if self._canceled(task_id):      # 已在 pending 阶段被取消
                return
            ctx = await self._prepare(task_id)     # analyzing
            if self._canceled(task_id):
                return
            await self._generate(ctx)              # generating
            if self._canceled(task_id):
                return
            await self._build(ctx)                 # building
            if self._canceled(task_id):
                return
            await self._finish(ctx)                # done
        except AppError as exc:
            await self._fail(task_id, exc)
        except Exception as exc:  # noqa: BLE001
            await self._fail(task_id, AppError(E_BLOCK_FAIL, f"生成流程异常: {exc}"))

    # ------------------------------------------------------------ 任务/事件基础设施

    def _task(self, task_id: str) -> dict:
        return self.storage.load_task(task_id)

    def _canceled(self, task_id: str) -> bool:
        return self._task(task_id).get("state") == "canceled"

    async def _push(self, task_id: str, event: str, data: dict) -> None:
        task = self._task(task_id)
        if not isinstance(task.get("events"), list):
            task["events"] = []
        task["events"].append({"event": event, "data": data})
        task["updatedAt"] = self.now()
        self.storage.save_task(task)

    async def _set_stage(self, task_id: str, state: str, stage_index: int) -> None:
        task = self._task(task_id)
        if task.get("state") == "canceled":   # 已取消：不复活状态
            return
        task["state"] = state
        task["stage"] = state
        task["stageIndex"] = stage_index
        task["stageTotal"] = len(STAGES)
        task["updatedAt"] = self.now()
        self.storage.save_task(task)
        await self._push(task_id, "task.stage", {
            "taskId": task_id, "stage": state,
            "stageIndex": stage_index, "stageTotal": len(STAGES),
        })

    def _add_progress(self, task_id: str, delta: float) -> None:
        task = self._task(task_id)
        task["progress"] = round(min(1.0, float(task.get("progress", 0.0)) + delta), 3)
        task["updatedAt"] = self.now()
        self.storage.save_task(task)

    def _relevant_weights(self, ctx: GenContext) -> dict:
        """本次实际执行的板块权重（跳过项不计入分母，进度归一到 1）。"""
        w = {
            "analysis": BLOCK_WEIGHTS["analysis"],
            "summary": BLOCK_WEIGHTS["summary"],
            "education": BLOCK_WEIGHTS["education"],
            "skills": BLOCK_WEIGHTS["skills"],
            "projects": BLOCK_WEIGHTS["projects"],
            "build": BLOCK_WEIGHTS["build"],
        }
        if ctx.resume.get("internship"):
            w["internship"] = BLOCK_WEIGHTS["internship"]
        if ctx.skill_extend_enabled:
            w["skill_extend"] = BLOCK_WEIGHTS["skill_extend"]
        return w

    # ------------------------------------------------------------ 阶段 1：analyzing

    async def _prepare(self, task_id: str) -> GenContext:
        task = self._task(task_id)
        resume_id = task["resumeId"]
        await self._set_stage(task_id, "analyzing", 0)

        resume = self.storage.load_resume(resume_id)
        jobs = resume.get("jobs") or []
        page_option = resume.get("pageOption", "one-page")
        identity = resume.get("identity", "intern")
        gen = resume.get("generation") or {}
        deep_search = bool(gen.get("deepSearch"))
        skill_extend_enabled = any(s.get("skillExtend") for s in (resume.get("skill") or []))
        project_count = (resume.get("contentPlan") or {}).get("projectCount") or 0

        # JD 分析：缓存复用（提交关卡已写入），未命中则重分析
        jd_key = GenCache.jd_key(jobs, page_option, identity,
                                 (self.rules.jobs_rules() or {}).get("version", "1.0"))
        factsheet = self.cache.get(jd_key)
        if not factsheet:
            fs = await self.analyzer.analyze(
                [Job(**j) for j in jobs], Resume(**resume), page_option, deep_search)
            factsheet = fs.model_dump(mode="json", by_alias=True)
            self.cache.set(jd_key, factsheet)

        ctx = GenContext(
            task_id=task_id, resume_id=resume_id, resume=resume, jobs=jobs,
            factsheet=factsheet, page_option=page_option,
            project_count=project_count, skill_extend_enabled=skill_extend_enabled,
            industry_rules=self._match_industry(factsheet),
            provider=self.provider, rules=self.rules, storage=self.storage,
            cache=self.cache, analyzer=self.analyzer, budget=self.budget,
            config=self.config,
        )

        # 联网搜索（deep_search=true，失败降级不阻塞 §5.6）
        if deep_search:
            if self.search_client.ready:
                try:
                    ctx.search_results = await self.search_client.search(
                        f"{factsheet.get('direction', '')} {factsheet.get('jdFocus', '')}",
                        max_results=5)
                except AppError as exc:
                    ctx.search_degraded = True
                    if exc.code != E_SEARCH:
                        raise
            else:
                ctx.search_degraded = True

        # 进度：analysis 完成
        if self._canceled(task_id):
            return ctx  # 已取消：不再推进进度/事件
        total = sum(self._relevant_weights(ctx).values())
        self._add_progress(task_id, BLOCK_WEIGHTS["analysis"] / total)
        await self._push(task_id, "block.done", {
            "taskId": task_id, "block": "analysis", "ok": True,
            "degraded": bool(ctx.search_degraded),
        })
        return ctx

    def _match_industry(self, factsheet: dict) -> dict:
        """按方向匹配行业规则（供块 prompt 的风格/评估参考）。"""
        direction = factsheet.get("direction", "")
        best, best_score = {}, 0
        for payload in self.rules.industries().values():
            score = sum(1 for kw in payload.get("keywords", []) if kw.lower() in direction.lower())
            if score > best_score:
                best, best_score = payload, score
        return best

    # ------------------------------------------------------------ 阶段 2：generating

    async def _generate(self, ctx: GenContext) -> None:
        await self._set_stage(ctx.task_id, "generating", 1)
        weights = self._relevant_weights(ctx)
        total = sum(weights.values())

        def _frac(name: str) -> float:
            return weights[name] / total if weights.get(name) else 0.0

        for layer in (LAYER1, LAYER2):
            blocks = [b for b in layer if weights.get(b) or b in ZERO_WEIGHT_BLOCKS]
            if not blocks:
                continue
            await asyncio.gather(*[
                self._run_block(ctx, b, _frac(b)) for b in blocks
            ])

    async def _run_block(self, ctx: GenContext, name: str, weight_frac: float) -> None:
        """执行单块：进度事件 + 失败降级（§5.6）。"""
        task_id = ctx.task_id
        if self._canceled(task_id):
            return
        await self._push(task_id, "block.progress", {
            "taskId": task_id, "block": name, "progress": 0.2,
        })
        gen_fn = BLOCK_GENERATORS[name]
        try:
            output = await gen_fn(ctx)
        except AppError as exc:
            output = {"degraded": True, "error": exc.message}
        except Exception as exc:  # noqa: BLE001
            output = {"degraded": True, "error": str(exc)}
        ctx.blocks[name] = output

        # 预算：记录自估行数（§5.3）
        self.budget.record_estimated(name, output)

        await self._push(task_id, "block.progress", {
            "taskId": task_id, "block": name, "progress": 1.0,
        })
        await self._push(task_id, "block.done", {
            "taskId": task_id, "block": name,
            "ok": not (output.get("degraded") or output.get("skipped")),
            "degraded": bool(output.get("degraded")),
            "skipped": bool(output.get("skipped")),
        })
        if not output.get("skipped"):
            self._add_progress(task_id, weight_frac)

    # ------------------------------------------------------------ 阶段 3：building

    async def _build(self, ctx: GenContext) -> None:
        await self._set_stage(ctx.task_id, "building", 2)
        blocks = ctx.blocks
        resume = self.storage.load_resume(ctx.resume_id)

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
        gen["stages"] = list(STAGES)
        gen["calibrationRef"] = getattr(self.budget, "path", None).name if getattr(self.budget, "path", None) else None
        resume["generation"] = gen

        # 模板装配（§6 building 步骤 1）：占位符替换/空区块删除/照片位/密度/水印 → html + config
        # 模板缺失为致命错误（E_TEMPLATE → failed，§5.6）
        assembler = Assembler(self.config.paths.templates_dir, self.storage)
        ctx.html, ctx.assembly_config = assembler.render(
            resume, ctx.blocks,
            density=resume.get("density", "normal"),
            watermark_mode=gen.get("watermarkMode", "practice"),
        )

        resume["updatedAt"] = self.now()
        self.storage.save_resume(resume)

        total = sum(self._relevant_weights(ctx).values())
        self._add_progress(ctx.task_id, BLOCK_WEIGHTS["build"] / total)
        await self._push(ctx.task_id, "block.done", {
            "taskId": ctx.task_id, "block": "build", "ok": True, "degraded": False,
        })

    # ------------------------------------------------------------ 终态

    async def _finish(self, ctx: GenContext) -> None:
        task = self._task(ctx.task_id)
        task["state"] = "done"
        task["progress"] = 1.0
        task["updatedAt"] = self.now()
        self.storage.save_task(task)
        await self._push(ctx.task_id, "task.done", {
            "taskId": ctx.task_id, "resumeId": ctx.resume_id,
            "config": ctx.assembly_config or {
                "pageOption": ctx.page_option,
                "density": ctx.resume.get("density", "normal"),
                "direction": ctx.factsheet.get("direction", ""),
                "contentPlan": ctx.resume.get("contentPlan", {}),
            },
            "html": ctx.html,  # P5 模板装配产出（前端可直接渲染）
        })

    async def _fail(self, task_id: str, exc: AppError) -> None:
        if self._canceled(task_id):
            return  # 已取消不覆盖
        task = self._task(task_id)
        task["state"] = "failed"
        task["error"] = {"code": exc.code, "message": exc.message}
        task["updatedAt"] = self.now()
        self.storage.save_task(task)
        await self._push(task_id, "task.failed", {
            "taskId": task_id, "error": {"code": exc.code, "message": exc.message},
        })
