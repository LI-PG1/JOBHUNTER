"""P3 核心逻辑回归验证（无 LLM 依赖，FakeProvider 模拟）：判定边界/容错/纯函数。

覆盖冒烟无法触达的分支：技能三档边界、关键词兜底、JD 分析→事实表、领域标签写回、
主题一致性（共享标签直通 / 语义兜底通过 / 40003 拦截）。

运行：.venv\\Scripts\\python.exe tests\\logic_check.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.errors import AppError, E_LLM, E_THEME_BLOCK
from app.core.rules import RulesLoader
from app.core.validation import project_count_for
from app.engine.analysis import JDAnalyzer, extract_json
from app.engine.skills import validate_skills
from app.schemas import Job, Resume

passed = 0


def ok(name, cond, detail=""):
    global passed
    assert cond, f"{name}: {detail}"
    passed += 1
    print(f"  [PASS] {name}")


class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def chat(self, messages, **kw):
        self.calls += 1
        return json.dumps(self.result, ensure_ascii=False)


loader = RulesLoader(str(ROOT / "rules"))
loader.load_all()

# 1) 数量硬性约束表（§3.5）
ok("一页/0实习 → 2 条", project_count_for("one-page", 0) == 2)
ok("一页/1实习 → 1 条", project_count_for("one-page", 1) == 1)
ok("一页/2实习 → 1 条", project_count_for("one-page", 2) == 1)
ok("两页/0实习 → 3 条", project_count_for("two-pages", 0) == 3)
ok("两页/1实习 → 2 条", project_count_for("two-pages", 1) == 2)
ok("两页/2实习 → 1 条", project_count_for("two-pages", 2) == 1)

# 2) JSON 容错提取
ok("围栏 JSON", extract_json('```json\n{"a": 1}\n```') == {"a": 1})
ok("前缀文本 JSON", extract_json('结果如下：{"a": 1} 完毕') == {"a": 1})

# 3) 技能三档边界 + 关键词兜底
jobs = [{"title": "大模型实习生", "jdText": "Python PyTorch Docker 大模型"}]
skills = [{"category": "专业技能", "name": "Python"}]
sr_rules = loader.skills_rules()


async def t1():
    p = FakeProvider({"score": 0.8, "reason": "强相关"})
    r = await validate_skills(p, skills, jobs, sr_rules)
    ok("LLM 0.8 → pass", r["verdict"] == "pass" and r["score"] == 0.8)

    p = FakeProvider({"score": 0.5, "reason": "部分相关"})
    r = await validate_skills(p, [{"category": "专业技能", "name": "Java"}], jobs, sr_rules)
    ok("LLM 0.5 无命中 → weak", r["verdict"] == "weak")

    p = FakeProvider({"score": 0.1, "reason": "不相关"})
    r = await validate_skills(p, [{"category": "专业技能", "name": "Java"}],
                              [{"title": "A", "jdText": "Python"}], sr_rules)
    ok("LLM 0.1 无命中 → block", r["verdict"] == "block")

    # 关键词兜底：技能名直接命中 JD，LLM 低分仍 pass
    p = FakeProvider({"score": 0.1, "reason": "评估"})
    r = await validate_skills(p, skills, jobs, sr_rules)
    ok("关键词兜底 → pass", r["verdict"] == "pass", str(r))


asyncio.run(t1())

# 4) JD 分析：行业匹配 + 关键词覆盖率 + 领域标签写回（FakeProvider 模拟 LLM）
resume = Resume(
    basicInfo={"name": "张三", "age": 24, "email": "a@b.com", "phone": "13800138000"},
    skill=[{"category": "专业技能", "name": "PyTorch"}, {"category": "工具与框架", "name": "Docker"}],
    project=[{"name": "RAG 知识库", "tech_stack": ["Milvus"]}],
)
jd = Job(title="大模型应用开发实习生",
         jdText="负责 LLM Agent 与 RAG 系统开发，熟悉 Python、PyTorch、Docker、vLLM")
p = FakeProvider({
    "direction": "AI Agent / LLM 应用",
    "coreSkills": ["大模型推理部署", "RAG 检索增强", "PyTorch"],
    "jdFocus": "智能体系统与 RAG 落地",
    "projectType": "智能体系统",
    "metricStyle": "延迟降至 100~200ms",
    "domainTags": ["大模型", "Agent", "RAG"],
    "keywordCoverage": 0.0,
})
analyzer = JDAnalyzer(p, loader)


async def t2():
    fs = await analyzer.analyze([jd], resume, "one-page")
    ok("方向解析", fs.direction == "AI Agent / LLM 应用")
    ok("数量映射写入", fs.quantity["projectCount"] == 2 and fs.quantity["internshipCount"] == 0)
    ok("领域标签写回 JD", jd.domain_tags == ["大模型", "Agent", "RAG"])
    ok("覆盖率计算（PyTorch 命中 1/3 → 0.33）", abs(fs.keyword_coverage - 0.33) < 1e-6, str(fs.keyword_coverage))

    # 主题一致性：共享标签 ≥1 → 直接通过（不调 LLM）
    await analyzer.check_theme(resume, [jd])
    ok("共享标签命中不调 LLM", p.calls == 1, f"calls={p.calls}")

    # 语义兜底：无共享标签但简历有领域标签 → 调 LLM，score ≥0.4 通过
    # 注意 mock 需同时充当 JD 分析（返回 domainTags）与主题评分（返回 score）
    _jd_result = {"direction": "后端开发", "domainTags": ["后端", "Java"],
                  "coreSkills": ["Java"], "jdFocus": "", "projectType": "", "metricStyle": ""}
    p2 = FakeProvider({**_jd_result, "score": 0.6, "reason": "同方向"})
    a2 = JDAnalyzer(p2, loader)
    resume2 = Resume(
        basicInfo={"name": "李四", "age": 25, "email": "b@c.com", "phone": "13800138001"},
        skill=[{"category": "专业技能", "name": "PyTorch"}],
        project=[{"name": "图像分类服务", "tech_stack": ["Docker"]}],
    )
    jd2 = Job(title="Java 后端开发", jdText="Java Spring 高并发")
    await a2.analyze([jd2], resume2, "one-page")
    await a2.check_theme(resume2, [jd2])
    ok("语义兜底通过（calls=2）", p2.calls == 2, f"calls={p2.calls}")

    # 语义兜底拒绝：score <0.4 → 40003 拦截
    p3 = FakeProvider({**_jd_result, "score": 0.2, "reason": "方向不同"})
    a3 = JDAnalyzer(p3, loader)
    try:
        await a3.check_theme(resume2, [jd2])
        ok("语义兜底拒绝 → 40003", False, "未拦截")
    except AppError as exc:
        ok("语义兜底拒绝 → 40003", exc.code == E_THEME_BLOCK, str(exc))


asyncio.run(t2())

# ================================================================ P4 生成引擎 DAG（§5.1/§5.4/§5.6）
import shutil
import tempfile
from datetime import datetime

from app.config import Config, Paths
from app.engine.budget import BudgetTracker
from app.engine.cache import GenCache
from app.engine.dag import GenerationRunner
from app.storage import Storage
from app.schemas import Task

JD_RESULT = {
    "direction": "AI Agent / LLM 应用",
    "coreSkills": ["大模型推理部署", "RAG"],
    "jdFocus": "智能体系统与 RAG 落地",
    "projectType": "智能体系统",
    "metricStyle": "延迟降至 100~200ms",
    "domainTags": ["大模型", "Agent"],
}


class DispatchProvider:
    """按 prompt 标记分发结果（模拟 JD 分析/自我评价/实习/项目 4 类 LLM 调用）。"""

    def __init__(self, project_result=None, fail_projects=False):
        self.jd_calls = 0
        self.fail_projects = fail_projects
        self.project_result = project_result

    async def chat(self, messages, **kw):
        text = json.dumps(messages, ensure_ascii=False)
        if "JD 分析器" in text:
            self.jd_calls += 1
            return json.dumps(JD_RESULT, ensure_ascii=False)
        if "自我评价撰写师" in text:
            return json.dumps({"sentences": [
                {"text": "扎实的工程能力与持续学习意愿。", "estimatedLines": 1},
                {"text": "熟悉大模型推理与 RAG 落地。", "estimatedLines": 2},
            ]})
        if "实习经历润色师" in text:
            return json.dumps({"items": [{
                "company": "某科技公司", "position": "算法实习生",
                "startMonth": "2024.06", "endMonth": "2024.09",
                "duties": [{"text": "优化推理服务延迟，吞吐提升 30%。", "estimatedLines": 2}],
            }]})
        if "项目经历撰写师" in text:
            if self.fail_projects:
                raise AppError(E_LLM, "模拟项目块 LLM 失败")
            return json.dumps(self.project_result or {"projects": [{
                "name": "Agent 调度平台", "role": "核心开发",
                "startMonth": "2025.01", "endMonth": "2025.06",
                "techStack": ["FastAPI", "vLLM"], "source": "polished",
                "items": [{"text": "设计分层并行 DAG 调度与实时进度上报。", "estimatedLines": 2},
                          {"text": "端到端吞吐提升 2 倍。", "estimatedLines": 1}],
            }]})
        raise AssertionError(f"未知 prompt 标记: {text[:80]}")


class DummySearch:
    ready = False


def make_runner(tmp: str, provider):
    cfg = Config(paths=Paths(data_dir=tmp, rules_dir=str(ROOT / "rules"),
                             templates_dir=str(ROOT / "templates")))
    storage = Storage(tmp)
    cache = GenCache(tmp)
    budget = BudgetTracker(tmp)
    runner = GenerationRunner(
        storage=storage, rules=loader, config=cfg, provider=provider,
        analyzer=JDAnalyzer(provider, loader), search_client=DummySearch(),
        cache=cache, budget=budget,
        now=lambda: datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    return storage, cache, runner


def seed_resume(storage: Storage, *, internship=True, honor=True) -> str:
    rid = storage.new_resume_id()
    data = {
        "id": rid, "identity": "intern", "pageOption": "one-page", "density": "normal",
        "basicInfo": {"name": "张三", "age": 24, "email": "a@b.com", "phone": "13800138000"},
        "education": [{"school": "安徽大学", "major": "应用统计", "degree": "学士",
                       "startMonth": "2020.09", "endMonth": "2024.06"}],
        "skill": [{"category": "专业技能", "name": "Python", "skillExtend": False},
                  {"category": "工具与框架", "name": "Docker", "skillExtend": False}],
        "internship": [{"company": "某科技公司", "position": "算法实习生",
                        "startMonth": "2024.06", "endMonth": "2024.09",
                        "duties": [{"text": "负责推理服务开发。"}]}] if internship else [],
        "project": [{"name": "RAG 知识库", "role": "开发", "startMonth": "2024.07", "endMonth": "2024.09",
                     "techStack": ["FastAPI", "Milvus"],
                     "items": [{"text": "构建检索增强问答系统。"}]}],
        "honor": [{"name": "国家奖学金", "time": "2023"}] if honor else [],
        "jobs": [{"title": "大模型应用开发实习生",
                  "jdText": "负责 LLM Agent 与 RAG 系统开发，熟悉 Python、PyTorch、Docker"}],
        "contentPlan": {"projectCount": project_count_for("one-page", 1)},
        "generation": {"deepSearch": False},
        "createdAt": "2026-01-01T00:00:00", "updatedAt": "2026-01-01T00:00:00",
    }
    storage.save_resume(data)
    return rid


def make_task(storage: Storage, rid: str) -> str:
    task = Task(id=storage.new_task_id(), resume_id=rid,
                state="pending", created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00")
    storage.save_task(task.model_dump(mode="json", by_alias=True))
    return task.id


async def t3():
    tmp = tempfile.mkdtemp(prefix="jl_agent_")
    try:
        # A) 全链路：JD 缓存写入 → 分层并行生成 → 装配回写 → done
        provider = DispatchProvider()
        storage, cache, runner = make_runner(tmp, provider)
        rid = seed_resume(storage)
        tid = make_task(storage, rid)
        await runner.run(tid)

        task = storage.load_task(tid)
        ok("任务终态 done", task["state"] == "done", str(task.get("error")))
        ok("进度收敛 1.0", abs(task["progress"] - 1.0) < 1e-6, str(task["progress"]))

        names = [e["event"] for e in task["events"]]
        ok("阶段事件 ×3", names.count("task.stage") == 3, str(names))
        for blk in ("analysis", "summary", "education", "internship", "skills", "honor", "projects", "build"):
            ok(f"block.done[{blk}] 已发", any(e["event"] == "block.done" and e["data"].get("block") == blk for e in task["events"]))
        ok("终态事件 task.done", "task.done" in names, str(names))

        ev_done = next((e for e in task["events"] if e["event"] == "task.done"), None)
        ok("task.done 注入装配 html", bool(ev_done) and "个人简历" in ev_done["data"].get("html", ""))
        ok("config 预算基线（projects）", bool(ev_done)
           and ev_done["data"]["config"]["blocks"].get("projects", 0) > 0)

        r = storage.load_resume(rid)
        ok("自我评价 2 句写回", len(r["summary"]) == 2)
        ok("实习润色写回（公司原值）", r["internship"][0]["company"] == "某科技公司" and "延迟" in r["internship"][0]["duties"][0]["text"])
        ok("项目条数 = 硬性约束 1", len(r["project"]) == 1)
        ok("项目来源 polished", r["project"][0]["source"] == "polished")
        ok("荣誉保留", r["honor"][0]["name"] == "国家奖学金")
        ok("装配元数据（一页 4 要点）", r["contentPlan"]["bulletCountPerProject"] == 4)

        jd_key = GenCache.jd_key(
            [j for j in r["jobs"]], "one-page", "intern",
            str(loader.jobs_rules().get("version", "1.0")))
        ok("JD 事实表已写缓存", cache.get(jd_key) is not None)

        # B) JD 缓存命中：同简历二次生成 → 不再调 JD 分析
        provider2 = DispatchProvider()
        storage2, cache2, runner2 = make_runner(tmp, provider2)
        tid2 = make_task(storage2, rid)
        await runner2.run(tid2)
        ok("二次生成 JD 分析缓存命中（jd_calls=0）", provider2.jd_calls == 0, f"jd_calls={provider2.jd_calls}")
        ok("二次任务终态 done", storage2.load_task(tid2)["state"] == "done")

        # C) 模块级失败隔离：项目块 LLM 失败 → 降级 + 种子兜底，整单继续
        provider3 = DispatchProvider(fail_projects=True)
        storage3, _, runner3 = make_runner(tmp, provider3)
        rid3 = seed_resume(storage3)
        tid3 = make_task(storage3, rid3)
        await runner3.run(tid3)
        ok("项目块失败 → 任务仍 done", storage3.load_task(tid3)["state"] == "done")
        ev = [e for e in storage3.load_task(tid3)["events"]
              if e["event"] == "block.done" and e["data"].get("block") == "projects"]
        ok("项目块事件标记降级", bool(ev) and ev[0]["data"].get("degraded") is True, str(ev))
        r3 = storage3.load_resume(rid3)
        ok("降级兜底：种子补足 1 条（user-input）", len(r3["project"]) == 1 and r3["project"][0]["source"] == "user-input", str(r3["project"]))

        # D) 荣誉为空 → 整块跳过，不覆盖简历
        provider4 = DispatchProvider()
        storage4, _, runner4 = make_runner(tmp, provider4)
        rid4 = seed_resume(storage4, honor=False)
        tid4 = make_task(storage4, rid4)
        await runner4.run(tid4)
        ev4 = [e for e in storage4.load_task(tid4)["events"]
               if e["event"] == "block.done" and e["data"].get("block") == "honor"]
        ok("荣誉空 → block.done skipped", bool(ev4) and ev4[0]["data"].get("skipped") is True, str(ev4))
        ok("荣誉空 → 简历未写空覆盖", storage4.load_resume(rid4).get("honor") in (None, []))

        # E) 取消：analyzing 阶段取消 → 不再产出 done
        provider5 = DispatchProvider()
        storage5, _, runner5 = make_runner(tmp, provider5)
        rid5 = seed_resume(storage5)
        tid5 = make_task(storage5, rid5)
        t = storage5.load_task(tid5)
        t["state"] = "canceled"
        t.setdefault("events", []).append({"event": "task.canceled", "data": {"taskId": tid5}})
        storage5.save_task(t)
        await runner5.run(tid5)
        ok("已取消 → 不覆盖终态", storage5.load_task(tid5)["state"] == "canceled")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


asyncio.run(t3())

# ================================================================ P5 适配闭环（§6 / §5.3 校准）
import statistics

from app.api.adjust import _decide_action, _next_density
from app.engine.assembly import Assembler


async def t4():
    tmp = tempfile.mkdtemp(prefix="jl_p5_")
    try:
        # 1) 判定纯函数（§6.7 阈值）
        ok("action=over（>100% 溢出）", _decide_action(1.1) == "over")
        ok("action=under（<75% 不足）", _decide_action(0.6) == "under")
        ok("action=ok（75%~100%）", _decide_action(0.85) == "ok")
        ok("density over → 更紧凑", _next_density("normal", "over") == "compact")
        ok("density under → 更松散", _next_density("normal", "under") == "loose")
        ok("density 边界不越界", _next_density("compact", "over") == "compact"
           and _next_density("loose", "under") == "loose")

        # 2) 多块校准（§5.3：校准行 + 中位数校正系数）
        bt = BudgetTracker(tmp)
        bt.record_estimated("summary", {"sentences": [{"text": "a", "estimatedLines": 3}]})
        bt.record_estimated("projects", {"projects": [{"items": [{"text": "b", "estimatedLines": 2}]}]})
        f1 = bt.record_actual("summary", 4)               # ratio = 4/3
        f2 = bt.record_actual("projects", 1)              # ratio = 1/2
        ok("summary 校正系数", abs(f1 - 1.333) < 0.001, str(f1))
        ok("projects 校正系数", abs(f2 - 0.5) < 0.001, str(f2))
        rows = json.loads((Path(tmp) / "calibration.json").read_text(encoding="utf-8"))
        ok("校准行落盘 ×2", len(rows) == 2 and rows[0]["blockType"] == "summary", str(rows))
        bt.record_estimated("summary", {"sentences": [{"text": "c", "estimatedLines": 2}]})
        bt.record_actual("summary", 1, estimated_lines=2)  # ratio = 0.5 → 中位数(1.333, 0.5)
        expect = round(statistics.median([1.333, 0.5]), 3)
        ok("校正系数 = 历史中位数", abs(bt.factor("summary") - expect) < 0.001, str(bt.factor("summary")))

        # 3) 模板装配（占位符替换/空区块删除/水印/照片位）
        asm = Assembler(str(ROOT / "templates"))
        resume = {
            "pageOption": "one-page", "direction": "AI Agent",
            "basicInfo": {"name": "张三", "phone": "13800138000", "email": "a@b.com"},
            "education": [{"school": "安徽大学", "major": "应用统计", "degree": "学士",
                           "startMonth": "2020.09", "endMonth": "2024.06"}],
            "internship": [{"company": "某科技公司", "position": "算法实习生",
                            "startMonth": "2024.06", "endMonth": "2024.09",
                            "duties": [{"text": "优化推理延迟。"}]}],
            "project": [{"name": "RAG 知识库", "role": "开发", "techStack": ["Milvus"],
                         "items": [{"text": "构建问答系统。"}]}],
            "skill": [{"category": "专业技能", "name": "Python"},
                      {"category": "工具与框架", "name": "Docker"}],
            "honor": [{"name": "国家奖学金"}],
            "summary": [{"text": "扎实的工程能力。"}],
        }
        blocks = {"projects": {"projects": [{"items": [{"text": "x", "estimatedLines": 2}]}]}}
        html, cfg = asm.render(resume, blocks, density="normal", watermark_mode="practice")
        ok("装配含姓名", "张三个人简历" in html)
        ok("data-density 注入", 'data-density="normal"' in html)
        ok("实习区块渲染", 'id="sec-internship"' in html)
        ok("项目区块渲染（含技术栈）", 'id="sec-projects"' in html and "技术栈" in html)
        ok("技能分类行", 'class="skill-cat">专业技能' in html)
        ok("荣誉区块渲染", 'id="sec-honors"' in html)
        ok("水印开启（practice）", 'class="watermark on"' in html)
        ok("config 预算基线 projects=2", cfg["blocks"]["projects"] == 2, str(cfg["blocks"]))

        r2 = dict(resume)
        r2["internship"], r2["honor"] = [], []
        html2, _ = asm.render(r2, {}, density="normal", watermark_mode="formal")
        ok("空实习区块删除", "sec-internship" not in html2)
        ok("空荣誉区块删除", "sec-honors" not in html2)
        ok("formal 无水印", "watermark on" not in html2)

        # 4) /api/adjust 全链路（TestClient + 临时 data 覆盖）
        from fastapi.testclient import TestClient

        from app.engine.cache import GenCache
        from app.main import app as app_
        from app.storage import Storage
        with TestClient(app_) as client:
            app_.state.storage = Storage(tmp)
            app_.state.gen_cache = GenCache(tmp)
            app_.state.config.paths.data_dir = tmp
            s = app_.state.storage
            tid = s.new_task_id()
            s.save_task({"id": tid, "resumeId": "r1", "state": "done", "progress": 1.0,
                         "stage": "building", "stageIndex": 2, "stageTotal": 3, "events": []})
            r = client.post("/api/adjust", json={
                "taskId": tid,
                "measurement": {"fillRatio": 1.2,
                                "blocks": [{"block": "projects", "actualLines": 9, "estimatedLines": 6}]},
                "config": {"density": "normal"}, "round": 1,
            })
            body = r.json()
            ok("adjust 200", r.status_code == 200, str(body))
            ok("action=over", body["data"]["action"] == "over", str(body["data"]))
            ok("density 建议 compact", body["data"]["config"]["density"] == "compact")
            ok("超差标记 drifted", body["data"]["drifted"] is True)
            t = s.load_task(tid)
            ev = [e for e in t["events"] if e["event"] == "task.adjust"]
            ok("task.adjust 事件持久化", len(ev) == 1 and ev[0]["data"]["action"] == "over", str(ev))
            rows2 = json.loads((Path(tmp) / "calibration.json").read_text(encoding="utf-8"))
            ok("adjust 实测校准行写入", any(x.get("actualLines") == 9 for x in rows2), str(rows2))
            r404 = client.post("/api/adjust", json={"taskId": "nope", "measurement": {"fillRatio": 0.9}})
            ok("adjust 任务不存在 → 40008", r404.status_code == 400 and r404.json()["code"] == 40008, str(r404.json()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


asyncio.run(t4())

# ================================================================ P6 编辑锁定（§5.5）+ data 标记装配
from app.api.resume import _leaf
from app.core.errors import E_PARAM


class EditedProvider(DispatchProvider):
    """项目 LLM 输出与种子同名，验证 edited 要点按名保留。"""

    async def chat(self, messages, **kw):
        text = json.dumps(messages, ensure_ascii=False)
        if "项目经历撰写师" in text:
            return json.dumps({"projects": [{
                "name": "RAG 知识库", "role": "开发",
                "startMonth": "2024.07", "endMonth": "2024.09",
                "techStack": ["FastAPI", "Milvus"], "source": "polished",
                "items": [{"text": "LLM 新写的一条要点。", "estimatedLines": 1}],
            }]})
        return await super().chat(messages, **kw)


def seed_edited(storage: Storage) -> str:
    rid = storage.new_resume_id()
    data = {
        "id": rid, "identity": "intern", "pageOption": "one-page", "density": "normal",
        "basicInfo": {"name": "张三", "age": 24, "email": "a@b.com", "phone": "13800138000"},
        "education": [{"school": "安徽大学", "major": "应用统计", "degree": "学士",
                       "startMonth": "2020.09", "endMonth": "2024.06"}],
        "internship": [{"company": "某科技公司", "position": "算法实习生",
                        "startMonth": "2024.06", "endMonth": "2024.09",
                        "duties": [{"text": "负责推理服务开发。", "criticality": "low", "estimatedLines": 1},
                                   {"text": "用户已改职责。", "criticality": "critical", "edited": True, "estimatedLines": 1}]}],
        "project": [{"name": "RAG 知识库", "role": "开发", "startMonth": "2024.07", "endMonth": "2024.09",
                     "techStack": ["FastAPI", "Milvus"],
                     "items": [{"text": "构建检索增强问答系统。", "criticality": "low", "estimatedLines": 1},
                               {"text": "用户已改的要点。", "criticality": "critical", "edited": True, "estimatedLines": 1}]}],
        "summary": [{"text": "用户已改的自我评价。", "criticality": "critical", "edited": True, "estimatedLines": 1},
                    {"text": "普通句子。", "criticality": "low", "estimatedLines": 1}],
        "honor": [],
        "jobs": [{"title": "大模型应用开发实习生",
                  "jdText": "负责 LLM Agent 与 RAG 系统开发，熟悉 Python、PyTorch、Docker"}],
        "contentPlan": {"projectCount": 1},
        "generation": {"deepSearch": False, "watermarkMode": "practice"},
        "createdAt": "2026-01-01T00:00:00", "updatedAt": "2026-01-01T00:00:00",
    }
    storage.save_resume(data)
    return rid


async def t5():
    tmp = tempfile.mkdtemp(prefix="jl_p6_")
    try:
        # ---------- A) 编辑锁定 / 解锁 / 重装配 API（§5.5 / §6） ----------
        from fastapi.testclient import TestClient

        from app.engine.cache import GenCache
        from app.main import app as app_
        with TestClient(app_) as client:
            app_.state.storage = Storage(tmp)
            app_.state.gen_cache = GenCache(tmp)
            app_.state.config.paths.data_dir = tmp
            app_.state.config.paths.templates_dir = str(ROOT / "templates")
            s = app_.state.storage
            rid = seed_edited(s)

            # summary 编辑 + 锁定
            r = client.put(f"/api/resume/{rid}/item",
                           json={"block": "summary", "index": 0, "text": "编辑后的自我评价"})
            body = r.json()
            ok("item 编辑 200", r.status_code == 200, str(body))
            d = body["data"]
            ok("summary 锁定（edited+critical）", d["resume"]["summary"][0]["edited"] is True
               and d["resume"]["summary"][0]["criticality"] == "critical", str(d["resume"]["summary"][0]))
            ok("summary 文本更新", d["resume"]["summary"][0]["text"] == "编辑后的自我评价")
            ok("重装配 html 带编辑定位标记", 'data-block="summary" data-index="0"' in d["html"])

            # 实习叶子编辑（index + subIndex）
            r = client.put(f"/api/resume/{rid}/item",
                           json={"block": "internship", "index": 0, "subIndex": 0, "text": "改过的职责"})
            d = client.put(f"/api/resume/{rid}/item",
                           json={"block": "project", "index": 0, "subIndex": 0, "text": "改过的要点"}).json()["data"]
            ok("项目叶子编辑锁定", d["resume"]["project"][0]["items"][0]["edited"] is True
               and d["resume"]["project"][0]["items"][0]["criticality"] == "critical")

            # 非法板块 / 越界 → 40001
            r = client.put(f"/api/resume/{rid}/item",
                           json={"block": "education", "index": 0, "text": "x"})
            ok("不可编辑板块 → 40001", r.status_code == 400 and r.json()["code"] == E_PARAM, str(r.json()))
            r = client.put(f"/api/resume/{rid}/item",
                           json={"block": "summary", "index": 99, "text": "x"})
            ok("下标越界 → 40001", r.status_code == 400 and r.json()["code"] == E_PARAM, str(r.json()))

            # 解锁
            r = client.post(f"/api/resume/{rid}/item/unlock", json={"block": "summary", "index": 0})
            d = r.json()["data"]
            ok("解锁 edited=false", d["resume"]["summary"][0]["edited"] is False, str(d["resume"]["summary"][0]))

            # 重装配渲染 + density 持久化
            r = client.post(f"/api/resume/{rid}/render", json={"density": "loose"})
            d = r.json()["data"]
            ok("render density 生效", 'data-density="loose"' in d["html"])
            ok("density 已持久化", s.load_resume(rid)["density"] == "loose")

            # _leaf 单元：不可编辑板块抛 40001
            try:
                _leaf({}, "skill", 0, None)
                ok("_leaf 拦截不可编辑板块", False, "未抛错")
            except AppError as exc:
                ok("_leaf 拦截不可编辑板块", exc.code == E_PARAM, str(exc))

        # ---------- B) 装配 data 标记 + summary 逐句渲染（§5.5 前端定位） ----------
        asm = Assembler(str(ROOT / "templates"))
        resume = {
            "pageOption": "one-page", "basicInfo": {"name": "张三", "phone": "1", "email": "a@b.com"},
            "education": [{"school": "安徽大学", "major": "应用统计", "degree": "学士",
                           "startMonth": "2020.09", "endMonth": "2024.06"}],
            "internship": [{"company": "某科技公司", "position": "算法实习生",
                            "startMonth": "2024.06", "endMonth": "2024.09",
                            "duties": [{"text": "职责 A。"}, {"text": "职责 B。"}]}],
            "project": [{"name": "RAG 知识库", "role": "开发", "techStack": ["Milvus"],
                         "items": [{"text": "要点 1。"}, {"text": "要点 2。"}]}],
            "summary": [{"text": "句子 1。"}, {"text": "句子 2。"}],
        }
        html, _ = asm.render(resume, {}, density="normal", watermark_mode="formal")
        ok("summary 逐句 data 标记", 'data-block="summary" data-index="0"' in html
           and 'data-block="summary" data-index="1"' in html)
        ok("实习职责 data 标记", 'data-block="internship" data-index="0" data-sub-index="1"' in html)
        ok("项目要点 data 标记", 'data-block="project" data-index="0" data-sub-index="1"' in html)
        ok("summary 容器 id=sec-summary", 'id="sec-summary"' in html)

        r2 = dict(resume); r2["pageOption"] = "two-pages"
        html2, _ = asm.render(r2, {}, density="normal", watermark_mode="formal")
        ok("两页版 summary 逐句 <p>", html2.count('class="summary-sentence"') == 2
           and '<p class="summary-sentence" data-block="summary" data-index="0">句子 1。</p>' in html2)

        # ---------- C) 生成器保留 edited 条目（§5.5） ----------
        provider = EditedProvider()
        storage, _, runner = make_runner(tmp, provider)
        rid2 = seed_edited(storage)
        tid2 = make_task(storage, rid2)
        await runner.run(tid2)
        ok("编辑态任务 done", storage.load_task(tid2)["state"] == "done")

        r = storage.load_resume(rid2)
        ok("编辑句保留原文", any(s.get("edited") and s["text"] == "用户已改的自我评价。"
                             for s in r["summary"]), str(r["summary"]))
        ok("编辑句 criticality=critical", any(s.get("edited") and s["criticality"] == "critical"
                                           for s in r["summary"]))
        ok("LLM 新句未标记 edited", all(not s.get("edited") for s in r["summary"] if "用户已改" not in s.get("text", "")))
        duties = r["internship"][0]["duties"]
        ok("编辑职责保留", any(d.get("edited") and d["text"] == "用户已改职责。" for d in duties), str(duties))
        p = r["project"][0]
        ok("编辑项目要点按名保留", any(i.get("edited") and i["text"] == "用户已改的要点。" for i in p["items"]), str(p["items"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


asyncio.run(t5())


# ================================================================ R7 设置控制台 / 导出 / 技能分类扩容
from app.core.errors import E_EXPORT


async def t6():
    tmp = tempfile.mkdtemp(prefix="jl_p7_")
    env_key = "DEEPSEEK_API_KEY"
    env_bak = os.environ.get(env_key)
    try:
        from fastapi.testclient import TestClient

        from app.engine.cache import GenCache
        from app.main import app as app_
        with TestClient(app_) as client:
            app_.state.storage = Storage(tmp)
            app_.state.gen_cache = GenCache(tmp)
            app_.state.config.paths.data_dir = tmp
            app_.state.config.paths.templates_dir = str(ROOT / "templates")
            s = app_.state.storage
            rid = seed_edited(s)
            env_actual = app_.state.config.provider.api_key_env

            # 设置：默认值 + 保存 API Key（脱敏）+ 默认深度搜索/水印
            r = client.get("/api/settings")
            d = r.json()["data"]
            ok("设置默认值（深度搜索开/水印无）", d["deepSearchDefault"] is True
               and d["watermarkDefault"] == "formal", str(d))
            r = client.put("/api/settings", json={"apiKey": "sk-test-1234567890abcd",
                                                  "deepSearchDefault": False,
                                                  "watermarkDefault": "practice"})
            d = r.json()["data"]
            ok("设置保存 + Key 脱敏", r.status_code == 200 and d["hasKey"] is True
               and "sk-t" in d["apiKeyMasked"] and "****" in d["apiKeyMasked"], str(d))
            ok("Key 已注入环境变量", os.getenv(env_actual) == "sk-test-1234567890abcd")
            r = client.get("/api/settings")
            d = r.json()["data"]
            ok("设置持久化回读", d["deepSearchDefault"] is False and d["watermarkDefault"] == "practice", str(d))
            r = client.put("/api/settings", json={"apiKey": ""})
            ok("清空 Key 生效", r.json()["data"]["hasKey"] is False)
            ok("清空后环境变量移除", os.getenv(env_actual) is None)

            # 多 Provider：新增 → 激活 → 回读脱敏 → 自检结构 → 删除
            r = client.put("/api/settings/providers", json={
                "name": "GLM", "baseUrl": "https://open.bigmodel.cn/api/paas/v4",
                "model": "glm-4-flash", "apiKey": "sk-glm-abcdef", "capabilities": "text", "enabled": True})
            d = r.json()["data"]
            pid = next((p for p in d["providers"] if p.get("name") == "GLM"), {}).get("id")
            ok("新增 provider 并自动激活", r.status_code == 200 and pid and d["activeProviderId"] == pid, str(d))
            r = client.post(f"/api/settings/providers/{pid}/activate")
            ok("显式激活 provider", r.status_code == 200 and r.json()["data"]["activeProviderId"] == pid, str(r.json()))
            r = client.get("/api/settings")
            d = r.json()["data"]
            ok("设置回读含 providers/activeProviderId",
               isinstance(d.get("providers"), list) and d["activeProviderId"] == pid, str(d))
            row = next((p for p in d["providers"] if p.get("id") == pid), {})
            ok("provider Key 脱敏", row.get("apiKey") is None
               and "sk-g" in row.get("apiKeyMasked", ""), str(d["providers"]))
            r = client.post("/api/settings/providers/test", json={
                "baseUrl": "https://invalid.example.invalid/v1", "model": "x", "apiKey": "sk-bad"})
            d = r.json()["data"]
            ok("配置自检返回结构", r.status_code == 200 and d["ok"] is False and "error" in d, str(d))
            r = client.delete(f"/api/settings/providers/{pid}")
            d = r.json()["data"]
            ok("删除 provider 生效", r.status_code == 200
               and all(p.get("id") != pid for p in d["providers"]), str(d["providers"]))

            # 可集成插件：注册表回读 → 启用 → 回读 → 非法 id 拦截
            r = client.get("/api/settings")
            d = r.json()["data"]
            pl = d.get("plugins") or []
            ok("插件注册表回读（6 个：OpenCLI/MediaCrawler/Agent-Reach/zhihu-cli/ats-checker/markdown-cv）",
               len(pl) == 6 and all(p.get("enabled") is False for p in pl) and
               {p["id"] for p in pl} == {"opencli", "mediacrawler", "agent-reach",
                                         "zhihu-cli", "ats-checker", "markdown-cv"},
               str([p["id"] for p in pl]))
            r = client.put("/api/settings/plugins/zhihu-cli", json={"enabled": True})
            d = r.json()["data"]
            on = next((p for p in d["plugins"] if p["id"] == "zhihu-cli"), {})
            ok("启用插件即时保存", r.status_code == 200 and on.get("enabled") is True, str(d))
            r = client.get("/api/settings")
            d = r.json()["data"]
            on = next((p for p in d["plugins"] if p["id"] == "zhihu-cli"), {})
            off = next((p for p in d["plugins"] if p["id"] == "ats-checker"), {})
            ok("插件状态持久化回读", on.get("enabled") is True and off.get("enabled") is False, str(d["plugins"]))
            r = client.put("/api/settings/plugins/not-exist", json={"enabled": True})
            ok("未知插件拦截", r.status_code == 400 and r.json()["code"] == 40001, str(r.json()))

            # 双层启动：第一层「一键配置」—— 仅检测不安装（auto_install=false），结构 + 状态联动
            r = client.post("/api/settings/plugins/zhihu-cli/configure?auto_install=false")
            d = r.json()["data"]
            on = next((p for p in d["plugins"] if p["id"] == "zhihu-cli"), {})
            ok("一键配置返回双层状态结构",
               r.status_code == 200 and "configured" in on and "installStatus" in on
               and on["installStatus"] in ("installed", "failed") and "features" in on
               and "featuresList" in on and len(on["featuresList"]) == 3 and "config" in on, str(on))
            # R20-2：配置成功与启用分离 —— configure 只写配置状态，不自动启用、不覆盖用户勾选
            ok("配置与启用分离（configure 保持用户手动勾选状态）",
               on["enabled"] is True and on["configured"] in (True, False), str(on))
            # R20-3：MediaCrawler 配置流程（git clone 目录检测）+ 扫码登录醒目提示
            mc = next((p for p in d["plugins"] if p["id"] == "mediacrawler"), {})
            ok("MediaCrawler 扫码登录醒目提示（loginNotice）",
               bool(mc.get("loginNotice")) and "扫码登录" in mc["loginNotice"], str(mc.get("loginNotice")))
            r = client.post("/api/settings/plugins/mediacrawler/configure?auto_install=false")
            d = r.json()["data"]
            mc = next((p for p in d["plugins"] if p["id"] == "mediacrawler"), {})
            ok("MediaCrawler git 目录检测（未克隆 → 配置失败）",
               r.status_code == 200 and mc["installStatus"] == "failed" and mc["configured"] is False, str(mc))
            ok("MediaCrawler 默认参数与功能模块写入",
               mc["config"].get("storeType") == "csv" and mc["features"].get("search") is True
               and len(mc["featuresList"]) == 3, str(mc))
            r = client.post("/api/settings/plugins/not-exist/configure")
            ok("未知插件一键配置拦截", r.status_code == 400 and r.json()["code"] == 40001, str(r.json()))

            # R20-2 单元：模拟已安装 → 配置成功（configured=True）→ 不自动启用，须用户手动勾选
            from unittest import mock
            from app.api import settings as settings_mod
            with mock.patch.object(settings_mod, "_plugin_installed", return_value=True):
                r = client.post("/api/settings/plugins/opencli/configure?auto_install=false")
            d = r.json()["data"]
            on = next((p for p in d["plugins"] if p["id"] == "opencli"), {})
            ok("配置成功（configured=True）不自动启用（R20-2 分离机制）",
               on["configured"] is True and on["enabled"] is False
               and on["installStatus"] == "installed", str(on))

            # 第二层：功能模块精细控制（持久化 + 未知模块拦截）
            r = client.put("/api/settings/plugins/zhihu-cli/features/hot", json={"enabled": True})
            d = r.json()["data"]
            on = next((p for p in d["plugins"] if p["id"] == "zhihu-cli"), {})
            ok("功能模块切换即时保存", r.status_code == 200 and on["features"].get("hot") is True, str(on["features"]))
            r = client.get("/api/settings")
            d = r.json()["data"]
            on = next((p for p in d["plugins"] if p["id"] == "zhihu-cli"), {})
            ok("功能模块状态持久化回读",
               on["features"].get("hot") is True and on["features"].get("search") is True, str(on["features"]))
            r = client.put("/api/settings/plugins/zhihu-cli/features/not-exist", json={"enabled": True})
            ok("未知功能模块拦截", r.status_code == 400 and r.json()["code"] == 40001, str(r.json()))

            # 技能分类扩容：新枚举值可通过 Resume 校验并保存
            r = client.post("/api/resume", json={
                "basicInfo": {"name": "李四", "age": 25, "email": "l@b.com", "phone": "13900000000"},
                "education": [{"school": "城大", "major": "CS", "degree": "硕士",
                               "startMonth": "2024.09", "endMonth": "2026.06"}],
                "skill": [{"category": "算法与模型", "name": "Transformer"}],
                "jobs": [{"title": "t", "jdText": "jd"}],
            })
            ok("新技能分类可保存", r.status_code == 200 and r.json()["code"] == 0, str(r.json()))

            # r17 时间校验：开始与结束均限 2015.01 ~ 2030.12
            from app.core.errors import E_EDU_TIME
            r = client.post("/api/resume", json={
                "basicInfo": {"name": "王五", "age": 24, "email": "w@b.com", "phone": "13900000001"},
                "education": [{"school": "城大", "major": "CS", "degree": "硕士",
                               "startMonth": "2014.12", "endMonth": "2015.06"}],
                "skill": [{"category": "专业技能", "name": "Python"}],
                "jobs": [{"title": "t", "jdText": "jd"}],
            })
            ok("开始时间早于 2015.01 被拦截", r.status_code == 400 and r.json()["code"] == E_EDU_TIME, str(r.json()))
            r = client.post("/api/resume", json={
                "basicInfo": {"name": "赵六", "age": 24, "email": "z@b.com", "phone": "13900000002"},
                "education": [{"school": "城大", "major": "CS", "degree": "硕士",
                               "startMonth": "2030.06", "endMonth": "2031.01"}],
                "skill": [{"category": "专业技能", "name": "Python"}],
                "jobs": [{"title": "t", "jdText": "jd"}],
            })
            ok("结束时间晚于 2030.12 被拦截", r.status_code == 400 and r.json()["code"] == E_EDU_TIME, str(r.json()))
            r = client.post("/api/resume", json={
                "basicInfo": {"name": "钱七", "age": 24, "email": "q@b.com", "phone": "13900000003"},
                "education": [{"school": "城大", "major": "CS", "degree": "硕士",
                               "startMonth": "2015.01", "endMonth": "2030.12"}],
                "skill": [{"category": "专业技能", "name": "Python"}],
                "jobs": [{"title": "t", "jdText": "jd"}],
            })
            ok("边界内时间可通过（2015.01 ~ 2030.12）", r.status_code == 200 and r.json()["code"] == 0, str(r.json()))

            # 导出：JSON / DOCX / 非法格式
            r = client.get(f"/api/resume/{rid}/export?format=json")
            ok("导出 JSON 200", r.status_code == 200
               and r.headers["content-type"].startswith("application/json"), str(r.headers.get("content-type")))
            try:
                payload = r.json()
                ok("导出 JSON 内容完整", payload.get("basicInfo", {}).get("name") == "张三", str(list(payload)[:5]))
            except Exception:
                ok("导出 JSON 内容完整", False, "非 JSON 响应")
            r = client.get(f"/api/resume/{rid}/export?format=docx")
            ok("导出 DOCX 200（python-docx）", r.status_code == 200
               and "wordprocessingml" in r.headers.get("content-type", "")
               and len(r.content) > 100, str(r.status_code))
            r = client.get(f"/api/resume/{rid}/export?format=pdf")
            ok("导出非法格式 → 40001", r.status_code == 400 and r.json()["code"] == E_PARAM, str(r.json()))

            # 列表字段：direction + file（本地存储位置）
            r = client.get("/api/resume")
            item = next((x for x in r.json()["data"]["items"] if x["id"] == rid), None)
            ok("列表含本地存储位置", item is not None and item["file"] == f"data/resumes/{rid}.json"
               and item["name"] == "张三", str(item))
    finally:
        if env_bak is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = env_bak
        shutil.rmtree(tmp, ignore_errors=True)


asyncio.run(t6())
print(f"\n逻辑验证: {passed} 通过")
