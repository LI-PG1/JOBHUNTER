"""review 回路单元测试：规则审核（禁用词/逻辑链/密度/口径）→ blocker → 带意见重写 → 复审。

无 LLM 依赖（FakeProvider 模拟），覆盖 review.py 全部行为：
- check_rules 四板块分支（projects/internship/summary/skill_extend）+ 编辑锁定 + 降级豁免
- review_block 回路：blocker 触发重写 / 复审未改善回退 / max_rewrite_rounds=0 不重写
- run_review 编排：reviewing 阶段 / block.review 事件 / 进度 / enabled=false 跳过
- config.review 配置消费（forbiddenWords / max_rewrite_rounds / enabled）

运行：python tests/test_review_loop.py
"""
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import ReviewCfg, load_config
from app.engine.blocks.base import GenContext
from app.engine.review import check_rules, review_block, run_review

passed = 0


def ok(name, cond, detail=""):
    global passed
    assert cond, f"{name}: {detail}"
    passed += 1
    print(f"  [PASS] {name}")


# ---------------------------------------------------------------- 数据与桩

# 含禁用词「我 / 保证」（config.review.forbiddenWords 命中）
DIRTY_SUMMARY = {
    "sentences": [
        {"text": "我负责了推荐系统开发，保证线上效果提升 30%",
         "criticality": "high", "estimatedLines": 2},
    ]
}
CLEAN_SUMMARY = {
    "sentences": [
        {"text": "负责推荐系统开发，线上转化率提升 30%",
         "criticality": "high", "estimatedLines": 2},
    ]
}

# 差项目：S/T/R 全无量化数字 + 短文本 → 逻辑链/密度/口径 blocker
BAD_PROJECT = {
    "projects": [{
        "name": "推荐系统",
        "items": [
            {"text": "负责推荐系统开发"},
            {"text": "大幅提升推荐效果"},
            {"text": "优化了模型结构"},
            {"text": "效果提升明显"},
        ],
    }]
}
# 好项目：完整 STAR，S 基线数字 / T 量化目标 / R 量化且≥T，每条 ≥35 等效字，无禁用词
GOOD_PROJECT = {
    "projects": [{
        "name": "推荐系统",
        "items": [
            {"text": "公司日请求量 1200 万次的推荐系统，初版命中率仅 45%，"
                     "用户点击转化率存在瓶颈，亟需算法迭代"},
            {"text": "目标将推荐命中率从 45% 提升至 95% 以上，点击转化率同步提升 20%，"
                     "覆盖全量线上流量"},
            {"text": "采用双塔召回与精排模型迭代，构建离线评估集与在线 A/B 实验体系，"
                     "按周灰度发布并监控核心指标"},
            {"text": "上线后推荐命中率提升至 96%，点击转化率提升 21%，"
                     "压测评估集覆盖全量样本且口径可复核"},
        ],
    }]
}


class FakeProvider:
    """按调用顺序返回 outputs；记录重写调用是否携带「上轮审核意见」。"""

    def __init__(self, outputs: list):
        self.outputs = list(outputs)
        self.calls = 0
        self.rewrite_feedbacks = []

    async def chat(self, messages, *, json_mode=False, max_tokens=4096, temperature=0.7):
        user = messages[-1]["content"]
        self.calls += 1
        if "上轮审核意见" in user:
            self.rewrite_feedbacks.append(user)
        idx = min(self.calls - 1, len(self.outputs) - 1)
        return json.dumps(self.outputs[idx], ensure_ascii=False)


class FakeRunner:
    """run_review 所需 runner 最小桩（不触 storage）。"""

    def __init__(self):
        self.stages = []
        self.events = []
        self.progress = 0.0
        self.canceled = False

    def _canceled(self, task_id):
        return self.canceled

    async def _set_stage(self, task_id, state, idx):
        self.stages.append((state, idx))

    def _add_progress(self, task_id, delta):
        self.progress = round(self.progress + delta, 3)

    def _relevant_weights(self, ctx):
        return {"analysis": 0.15, "summary": 0.10, "education": 0.05,
                "skills": 0.10, "projects": 0.35, "build": 0.10}

    async def _push(self, task_id, event, data):
        self.events.append((event, data))


def make_ctx(provider, cfg, resume=None, project_count=0):
    resume = resume or {
        "summary": [], "education": [], "internship": [], "skill": [],
        "project": [], "jobs": [], "pageOption": "one-page", "density": "normal",
    }
    return GenContext(
        task_id="t-review", resume_id="r-mock", resume=resume, jobs=[],
        factsheet={"direction": "LLM 应用", "jdFocus": "推荐系统开发"},
        industry_rules={}, provider=provider, config=cfg, project_count=project_count,
    )


def blockers_of(issues):
    return [x for x in issues if x.get("severity") == "blocker"]


# ---------------------------------------------------------------- 用例 1：配置消费

def test_config(cfg):
    ok("config.review.enabled 默认 true", cfg.review.enabled is True)
    ok("config.review.max_rewrite_rounds 默认 1", cfg.review.max_rewrite_rounds == 1)
    ok("config.review.forbiddenWords 含「我/保证」",
       "我" in cfg.review.forbidden_words and "保证" in cfg.review.forbidden_words)


# ---------------------------------------------------------------- 用例 2：check_rules 分支

def test_check_rules(cfg):
    # summary：禁用词 blocker
    ctx = make_ctx(FakeProvider([]), cfg)
    issues = check_rules(ctx, "summary", DIRTY_SUMMARY)
    bs = blockers_of(issues)
    ok("summary 命中 2 个禁用词 blocker",
       len(bs) == 2 and all(b["code"] == "forbidden" for b in bs),
       f"实际 {[(b['code'], b['message']) for b in bs]}")

    # summary：占位符兜底正则（不在词表，代码内置）
    ctx2 = make_ctx(FakeProvider([]), cfg)
    issues2 = check_rules(ctx2, "summary", {"sentences": [{"text": "待补充内容"}]})
    ok("占位符「待补充」命中 blocker",
       any(b["code"] == "forbidden" and "占位符" in b["message"] for b in blockers_of(issues2)))

    # summary：纯技术文本零 issue
    ctx3 = make_ctx(FakeProvider([]), cfg)
    clean = {"sentences": [{"text": "负责推荐系统开发，线上转化率提升 30%"}]}
    ok("干净文本零 issue", check_rules(ctx3, "summary", clean) == [])

    # 编辑锁定：edited 条目跳过禁用词审核
    ctx4 = make_ctx(FakeProvider([]), cfg)
    edited = {"sentences": [{"text": "我负责了项目", "edited": True}]}
    ok("edited 条目跳过禁用词审核", check_rules(ctx4, "summary", edited) == [])

    # 降级豁免：degraded 输出不审核
    ctx5 = make_ctx(FakeProvider([]), cfg)
    degraded = {**DIRTY_SUMMARY, "degraded": True}
    ok("degraded 板块豁免审核", check_rules(ctx5, "summary", degraded) == [])

    # projects：差项目命中逻辑链 blocker
    ctx6 = make_ctx(FakeProvider([]), cfg)
    issues6 = check_rules(ctx6, "projects", BAD_PROJECT)
    ok("差项目命中 star_chain blocker",
       any(b["code"] == "star_chain" for b in blockers_of(issues6)),
       f"实际 {[b['code'] for b in blockers_of(issues6)]}")

    # projects：好项目零 blocker（warning 不影响 pass）
    ctx7 = make_ctx(FakeProvider([]), cfg)
    issues7 = check_rules(ctx7, "projects", GOOD_PROJECT)
    ok("好项目零 blocker", blockers_of(issues7) == [],
       f"实际 {[b['code'] for b in blockers_of(issues7)]}")

    # internship：短文本 + 禁用词
    ctx8 = make_ctx(FakeProvider([]), cfg)
    issues8 = check_rules(ctx8, "internship",
                          {"items": [{"duties": [{"text": "我处理了日常事务"}]}]})
    ok("internship 命中密度/禁用词 blocker",
       any(b["code"] == "density_min" for b in blockers_of(issues8)) and
       any(b["code"] == "forbidden" for b in blockers_of(issues8)))

    # skill_extend：分类数 2 → blocker；4 → 通过
    ctx9 = make_ctx(FakeProvider([]), cfg)
    issues9 = check_rules(ctx9, "skill_extend",
                          {"skills": [{"category": "专业技能"}, {"category": "工具与框架"}]})
    ok("skill_extend 分类数 2 命中 quantity blocker",
       any(b["code"] == "quantity" for b in blockers_of(issues9)))
    ctx10 = make_ctx(FakeProvider([]), cfg)
    issues10 = check_rules(ctx10, "skill_extend",
                           {"skills": [{"category": "专业技能"}, {"category": "工具与框架"},
                                       {"category": "语言能力"}, {"category": "推理部署"}]})
    ok("skill_extend 分类数 4 通过", blockers_of(issues10) == [])


# ---------------------------------------------------------------- 用例 3：review_block 回路

async def test_review_block(cfg):
    # 禁用词 blocker → 带意见重写 → 复审 pass
    provider = FakeProvider([CLEAN_SUMMARY])
    ctx = make_ctx(provider, cfg)
    ctx.blocks["summary"] = dict(DIRTY_SUMMARY)
    r = await review_block(ctx, "summary")
    ok("重写触发：rounds=1, rewritten=True",
       r["rounds"] == 1 and r["rewritten"] is True, f"实际 {r}")
    ok("复审通过：verdict=pass, blockerCount=0",
       r["verdict"] == "pass" and r["blockerCount"] == 0)
    ok("重写调用携带上轮审核意见", len(provider.rewrite_feedbacks) == 1)
    texts = [s["text"] for s in ctx.blocks["summary"]["sentences"]]
    ok("ctx.blocks 已替换为重写版本（无禁用词）",
       ctx.blocks["summary"]["sentences"] == CLEAN_SUMMARY["sentences"], f"实际 {texts}")

    # 复审未改善（重写仍含同量禁用词）→ 回退保留原版本
    still_bad = {"sentences": [{"text": "我再次负责了推荐系统，保证交付质量"}]}
    provider2 = FakeProvider([still_bad])
    ctx2 = make_ctx(provider2, cfg)
    ctx2.blocks["summary"] = dict(DIRTY_SUMMARY)
    r2 = await review_block(ctx2, "summary")
    ok("重写未改善 → accept_with_issues 且回退原版",
       r2["verdict"] == "accept_with_issues" and r2["rewritten"] is True and
       ctx2.blocks["summary"] == DIRTY_SUMMARY, f"实际 {r2}")

    # max_rewrite_rounds=0：blocker 不触发重写（保留原词表）
    cfg0 = replace(cfg, review=ReviewCfg(enabled=True, max_rewrite_rounds=0,
                                         forbidden_words=cfg.review.forbidden_words))
    provider3 = FakeProvider([CLEAN_SUMMARY])
    ctx3 = make_ctx(provider3, cfg0)
    ctx3.blocks["summary"] = dict(DIRTY_SUMMARY)
    r3 = await review_block(ctx3, "summary")
    ok("rounds=0 不重写：verdict=accept_with_issues, LLM 零调用",
       r3["verdict"] == "accept_with_issues" and r3["rewritten"] is False and
       provider3.calls == 0, f"实际 {r3}")

    # 规则链 blocker（差项目）→ 重写 → 好项目 pass
    provider4 = FakeProvider([GOOD_PROJECT])
    ctx4 = make_ctx(provider4, cfg, project_count=1)
    ctx4.blocks["projects"] = dict(BAD_PROJECT)
    r4 = await review_block(ctx4, "projects")
    ok("差项目规则 blocker 触发重写 → pass",
       r4["verdict"] == "pass" and r4["rewritten"] is True, f"实际 {r4}")
    ok("项目内容已替换为 STAR 完整版本",
       [x["text"] for x in ctx4.blocks["projects"]["projects"][0]["items"]]
       == [x["text"] for x in GOOD_PROJECT["projects"][0]["items"]],
       f"实际 {[x['text'] for x in ctx4.blocks['projects']['projects'][0]['items']]}")


# ---------------------------------------------------------------- 用例 4：run_review 编排

async def test_run_review(cfg):
    provider = FakeProvider([CLEAN_SUMMARY])
    ctx = make_ctx(provider, cfg)
    ctx.blocks["summary"] = dict(DIRTY_SUMMARY)
    runner = FakeRunner()
    await run_review(runner, ctx)

    ok("推进 reviewing 阶段", ("reviewing", 2) in runner.stages)
    r = ctx.review_summary["results"][0]
    ok("review_summary 记录 pass/rewritten",
       r["block"] == "summary" and r["verdict"] == "pass" and r["rewritten"] is True)
    ev = next(e for e in runner.events if e[0] == "block.review")[1]
    ok("block.review 事件载荷完整",
       ev["block"] == "summary" and ev["verdict"] == "pass" and
       ev["rounds"] == 1 and ev["rewritten"] is True and ev["blockerCount"] == 0)
    ok("审核完成推进度", runner.progress > 0)

    # enabled=false：整阶段跳过
    provider2 = FakeProvider([CLEAN_SUMMARY])
    ctx2 = make_ctx(provider2, replace(cfg, review=ReviewCfg(enabled=False)))
    ctx2.blocks["summary"] = dict(DIRTY_SUMMARY)
    runner2 = FakeRunner()
    await run_review(runner2, ctx2)
    ok("enabled=false 跳过：无阶段/事件/进度/review_summary",
       runner2.stages == [] and runner2.events == [] and runner2.progress == 0.0
       and ctx2.review_summary == {})


async def main() -> None:
    cfg = load_config()
    test_config(cfg)
    test_check_rules(cfg)
    await test_review_block(cfg)
    await test_run_review(cfg)
    print(f"\n逻辑验证: {passed} 通过")


if __name__ == "__main__":
    asyncio.run(main())
