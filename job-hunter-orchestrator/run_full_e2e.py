"""JOBHUNTER 大脑全链路测试：模拟用户在各个阶段的输入

覆盖用户输入的三类维度：
- 输入方式：一句话自然语言 / 半结构化（方向：…；技能：…；经历：…）
- 输入组合：画像缺失追问补充、N9 确认/修改/拒绝、skip_confirm、反馈环收敛/降级
- 输入内容：不同方向/学历/技能/经历/城市/求职类型

运行：
    cd job-hunter-orchestrator
    python run_full_e2e.py

输出：_设计文档/大脑全链路测试报告-YYYYMMDD.md
"""
import datetime
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from graph import nodes
from graph.build import build_graph

REPORT_DIR = Path(__file__).resolve().parent.parent / "_设计文档"


# ---------------------------------------------------------------------------
# 场景定义：每个场景 = 一组用户输入（初始诉求 + 各 HITL 点的用户回答 + 期望）
# ---------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "S1",
        "name": "完整画像·首轮达标·用户确认定稿",
        "goal": "我硕士在读，自动驾驶方向，熟悉决策规划算法，掌握C++和Python，做过轨迹预测项目，想找实习",
        "config": {},
        "submission_input": {"city": "深圳", "max_results": 10, "company_types": ["大型"]},
        "user_script": {"confirm": [{"action": "approve"}]},
        "expect": {
            "gate_verdict": "pass", "match_round": 0, "resume_final": "approved",
            "profile_ask_round": 0, "missing_empty": True, "report": True,
            "errors_empty": True, "interactions": 1, "submission_plan": True,
        },
    },
    {
        "id": "S2",
        "name": "画像缺失·追问补充·继续全流程",
        "goal": "我本科在读，想找实习",
        "config": {},
        "user_script": {
            "ask_profile": [{"skills": ["决策规划", "C++", "Python", "轨迹预测"],
                             "experience": [{"name": "轨迹预测项目", "desc": "轨迹预测算法实现"}]}],
            "confirm": [{"action": "approve"}],
        },
        "expect": {
            "gate_verdict": "pass", "profile_ask_round": 1, "missing_empty": True,
            "resume_final": "approved", "report": True, "errors_empty": True,
            "interactions": 2, "submission_plan": True,
        },
    },
    {
        "id": "S3",
        "name": "画像缺失·追问两轮仍缺·终止并记录",
        "goal": "我是应届生，想找一份工作",
        "config": {},
        "user_script": {"ask_profile": [{"skip": True}, {"skip": True}]},
        "expect": {
            "profile_ask_round": 2, "missing_empty": False, "report": False,
            "resume_final": None, "interactions": 2, "submission_plan": False,
        },
    },
    {
        "id": "S4",
        "name": "匹配首轮达标·N9 用户提修改意见·再次确认",
        "goal": "我硕士在读，做过感知项目，会Python，找实习",
        "config": {},
        "user_script": {
            "confirm": [
                {"action": "modify", "feedback": [{"gap": "缺少PyTorch表述", "suggestion": "补充PyTorch技能", "priority": "high"}]},
                {"action": "approve"},
            ],
        },
        "expect": {
            "gate_verdict": "pass", "match_round": 1, "resume_round_min": 2,
            "resume_final": "approved", "report": True, "errors_empty": True,
            "feedback_has_modify": True, "interactions": 2, "submission_plan": True,
        },
    },
    {
        "id": "S5",
        "name": "匹配达标·N9 用户拒绝·记录原因结束",
        "goal": "我硕士在读，自动驾驶方向，熟悉决策规划算法，掌握C++和Python，做过轨迹预测项目，想找实习",
        "config": {},
        "user_script": {"confirm": [{"action": "reject", "reason": "方向与职业规划不符"}]},
        "expect": {
            "gate_verdict": "pass", "resume_final": "rejected", "reject_reason": "方向与职业规划不符",
            "report": False, "interactions": 1, "submission_plan": True,
        },
    },
    {
        "id": "S6",
        "name": "匹配持续不达标·3轮后降级继续",
        "goal": "我本科在读，做过C++图像处理开发，想找大模型方向实习",
        "config": {},
        "user_script": {"confirm": [{"action": "approve"}]},
        "expect": {
            "gate_verdict": "accept_with_issues", "match_round": 2,
            "resume_final": "approved", "report": True, "errors_contain": ["降级"],
            "interactions": 1, "submission_plan": True,
        },
    },
    {
        "id": "S7",
        "name": "skip_confirm 配置·全自动跑完（无人工交互）",
        "goal": "我硕士在读，自动驾驶方向，熟悉决策规划算法，掌握C++和Python，做过轨迹预测项目，想找实习",
        "config": {"skip_confirm": True},
        "user_script": {},
        "expect": {
            "gate_verdict": "pass", "resume_final": "auto-approved(mock)",
            "report": True, "errors_empty": True, "interactions": 0, "submission_plan": True,
        },
    },
]

# S8：输入内容/方式变体（解析层校验，不跑全图）
PARSE_VARIANTS = [
    {"goal": "方向：大模型；技能：Python、Agent、RAG；经历：做过RAG问答项目；类型：实习；城市：上海",
     "expect": {"direction": "大模型", "skills": ["python", "agent", "rag", "大模型"],
                "experience": 1, "type": "实习", "city": "上海"}},
    {"goal": "我研究生在读，秋招，想做感知算法，会Python和PyTorch，做过目标检测项目",
     "expect": {"direction": "感知", "skills": ["python", "pytorch", "目标检测", "感知"],
                "experience": 1, "type": "秋招", "city": "不限"}},
    {"goal": "帮我找一份数据分析实习",
     "expect": {"direction": "数据分析", "skills": ["数据分析"], "experience": 0,
                "type": "实习", "city": "不限"}},
    {"goal": "做过轨迹预测项目，熟悉决策规划、C++，目标深圳",
     "expect": {"direction": "决策规划", "skills": ["c++", "轨迹预测", "决策规划"],
                "experience": 1, "type": "实习", "city": "深圳"}},
]


# ---------------------------------------------------------------------------
# 用户模拟器：在 HITL 点（ask_profile / confirm_resume）按场景脚本给出用户输入
# ---------------------------------------------------------------------------
class UserSimulator:
    def __init__(self, script):
        self.script = script or {}
        self.log = []
        self._confirm_idx = 0

    def answer(self, payload):
        itype = payload.get("type")
        if itype == "ask_profile":
            round_ = payload.get("ask_round", 0)
            answers = self.script.get("ask_profile") or []
            ans = answers[round_] if round_ < len(answers) else {"skip": True}
        elif itype == "confirm_resume":
            confirms = self.script.get("confirm") or []
            idx = self._confirm_idx
            self._confirm_idx += 1
            ans = confirms[idx] if idx < len(confirms) else {"action": "approve"}
        else:
            ans = {"skip": True}
        self.log.append({"type": itype, "payload": payload, "answer": ans})
        return ans


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def _check(name, cond, detail=""):
    return {"name": name, "ok": bool(cond), "detail": detail}


def verify_scenario(sc, final, sim):
    exp = sc.get("expect", {})
    ua = final.get("user_approvals", {})
    checks = []
    cs = checks.append

    def got(key, default=None):
        return final.get(key, default)

    cs(_check("画像追问轮数", got("profile_ask_round", 0) == exp.get("profile_ask_round", 0),
              f"ask_round={final.get('profile_ask_round')}"))
    cs(_check("画像完整", (not final.get("missing_fields")) == exp.get("missing_empty", True),
              f"missing={final.get('missing_fields')}"))
    if exp.get("gate_verdict") is not None:
        cs(_check("匹配判定", got("gate_verdict") == exp["gate_verdict"],
                  f"verdict={final.get('gate_verdict')}"))
    if exp.get("match_round") is not None:
        cs(_check("匹配轮次", (got("match_round") or 0) == exp["match_round"],
                  f"match_round={final.get('match_round') or 0}"))
    if exp.get("resume_round_min"):
        cs(_check("简历迭代轮次", (final.get("resume_round") or 0) >= exp["resume_round_min"],
                  f"resume_round={final.get('resume_round')}"))
    if exp.get("resume_final") is not None:
        cs(_check("定稿结果", ua.get("resume_final") == exp["resume_final"],
                  f"resume_final={ua.get('resume_final')}"))
    if exp.get("reject_reason"):
        cs(_check("拒绝原因", ua.get("reject_reason") == exp["reject_reason"],
                  f"reason={ua.get('reject_reason')}"))
    if exp.get("report") is not None:
        cs(_check("总报告产出", bool(final.get("report")) == exp["report"],
                  f"report={'有' if final.get('report') else '无'}"))
    if exp.get("errors_empty") is not None:
        cs(_check("无错误", exp["errors_empty"] == (not final.get("errors")),
                  f"errors={final.get('errors')}"))
    for sub in exp.get("errors_contain", []):
        cs(_check(f"错误包含「{sub}」", any(sub in e for e in final.get("errors", [])),
                  f"errors={final.get('errors')}"))
    if exp.get("feedback_has_modify"):
        fb = final.get("resume_feedback", [])
        cs(_check("含用户修改意见", any(f.get("suggestion") == "补充PyTorch技能" for f in fb),
                  f"feedback={fb}"))
    if exp.get("interactions") is not None:
        cs(_check("用户交互次数", len(sim.log) == exp["interactions"],
                  f"interactions={len(sim.log)}"))
    if exp.get("submission_plan") is not None:
        plan = final.get("submission_plan") or {}
        cs(_check("投递清单产出", bool(plan) == exp["submission_plan"],
                  f"plan={'有' if plan else '无'}"))
        if exp.get("submission_plan") and plan:
            cs(_check("清单状态", plan.get("status") in ("pending_review", "confirmed"),
                      f"status={plan.get('status')}"))
            cs(_check("清单分档汇总", plan.get("summary", {}).get("total") == len(plan.get("items", [])),
                      f"total={plan.get('summary', {}).get('total')}"))
    return checks


# ---------------------------------------------------------------------------
# 场景执行
# ---------------------------------------------------------------------------
def run_scenario(sc):
    app = build_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": sc["id"]}}
    sim = UserSimulator(sc.get("user_script", {}))
    path = []
    t0 = time.perf_counter()

    initial = {"user_goal": sc["goal"], "config": sc.get("config", {})}
    if sc.get("submission_input"):
        initial["submission_input"] = sc["submission_input"]
    cur = initial
    for _ in range(30):  # 防死循环
        for chunk in app.stream(cur, cfg, stream_mode="updates"):
            path.extend(chunk.keys())
        snap = app.get_state(cfg)
        if snap.interrupts:
            payload = snap.interrupts[0].value
            cur = Command(resume=sim.answer(payload))
        else:
            break

    final = app.get_state(cfg).values
    elapsed_ms = (time.perf_counter() - t0) * 1000
    checks = verify_scenario(sc, final, sim)
    return {
        "id": sc["id"], "name": sc["name"], "goal": sc["goal"],
        "config": sc.get("config", {}), "path": path, "interactions": sim.log,
        "final": final, "checks": checks, "elapsed_ms": elapsed_ms,
        "ok": all(c["ok"] for c in checks),
    }


def run_parse_variants():
    rows = []
    for i, v in enumerate(PARSE_VARIANTS, 1):
        profile, jobs = nodes._parse_goal_mock(v["goal"])
        exp = v["expect"]
        checks = []
        cs = checks.append
        got_dir = profile["preference"]["direction"]
        got_skills = [s.lower() for s in profile["skills"]]
        got_type = profile["preference"]["type"]
        got_city = profile["preference"]["city"]
        cs(_check("方向识别", got_dir == exp["direction"], f"direction={got_dir}"))
        cs(_check("技能识别", all(s in got_skills for s in exp["skills"]), f"skills={got_skills}"))
        cs(_check("经历识别", len(profile["experience"]) == exp["experience"],
                  f"experience={profile['experience']}"))
        cs(_check("类型识别", got_type == exp["type"], f"type={got_type}"))
        cs(_check("城市识别", got_city == exp["city"], f"city={got_city}"))
        rows.append({"variant": i, "goal": v["goal"], "profile": profile,
                     "jobs": jobs, "checks": checks, "ok": all(c["ok"] for c in checks)})
    return rows


def run_export_smoke(results):
    """Q10e 导出 smoke：用场景产出的 submission_plan 渲染范本格式 HTML，断言关键标记 + 写示例文件。"""
    plan = next((r["final"].get("submission_plan") for r in results
                 if r["final"].get("submission_plan")), None)
    if not plan:
        return {"ok": False, "checks": [_check("导出 smoke", False, "无可用清单")], "out": None}
    from export.submission_html import render_submission_plan_html, export_submission_plan_html
    html_text = render_submission_plan_html(plan, "line-mock", {})
    checks = [_check(f"HTML 含「{m}」", m in html_text) for m in
              ["<!DOCTYPE html>", "投递清单", "@page", "sources"]]
    present_tiers = sorted({it.get("tier") for it in plan.get("items", [])})
    for t in present_tiers:
        checks.append(_check(f"HTML 含「tier-{t}」分档表", f"tier-{t}" in html_text))
    out = export_submission_plan_html(plan, "line-mock", {}, REPORT_DIR)
    checks.append(_check("示例文件写入", out.exists(), f"path={out.name}"))
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "out": out}


def run_q10_boundary():
    """S9 Q10 边界校验：直接构造 state 调 build_submission_plan / gate_match / confirm_resume（mock interrupt）。
    覆盖：max_results 防御（缺失/文本/0/负数/超大/截断）、企业类型过滤（全勾归一化/部分勾选/前端∪画像并集/
    非法类型全剔除/空 match_results）、阈值恰好、N9 未知 action、导出空清单与 HTML 转义。"""
    from unittest import mock

    def cand(job_id, company, score):
        return {"job_id": job_id, "title": f"{company}-岗位", "company": company,
                "score": score, "reasons": [f"{company}理由"]}

    # 候选覆盖 6 类企业（命中 _enterprise_type_of 关键字表）
    cands = [
        cand("j1", "中石油", 95), cand("j2", "中国联通", 88), cand("j3", "腾讯", 82),
        cand("j4", "元戎", 75), cand("j5", "戴盟", 65), cand("j6", "微软", 92),
    ]

    def pstate(submission_input=None, profile=None, match_results=None):
        return {"match_results": cands if match_results is None else match_results,
                "profile": profile or {}, "resume": {},
                "submission_input": submission_input or {}}

    def build(submission_input=None, profile=None, match_results=None):
        return nodes.build_submission_plan(pstate(submission_input, profile, match_results))["submission_plan"]

    rows = []

    # ---- max_results 防御（0/负数不再产生负切片错乱） ----
    mr_cases = [("缺失→默认20", None, 20), ("文本 abc→默认20", "abc", 20),
                ("0→默认20", 0, 20), ("负数-5→默认20", -5, 20),
                ("超大9999→上限200", 9999, 200), ("合法1→保留1", 1, 1)]
    rows.append({"name": "max_results 防御", "checks": [
        _check(n, build({"max_results": v})["filters"]["max_results"] == exp,
               f"max_results={build({'max_results': v})['filters']['max_results']}")
        for n, v, exp in mr_cases
    ] + [_check("合法1截断为1条", len(build({"max_results": 1})["items"]) == 1,
                f"items={len(build({'max_results': 1})['items'])}")]})

    # ---- 企业类型过滤（对齐 Q10f 契约） ----
    p = build({"company_types": list(nodes.COMPANY_TYPES_ALL)})
    rows.append({"name": "全勾6类→归一化不限", "checks": [
        _check("归一化为不限", p["filters"]["company_types"] == "不限", f"filters={p['filters']['company_types']}"),
        _check("全部 6 条保留", len(p["items"]) == 6, f"items={len(p['items'])}"),
    ]})
    p = build({"company_types": ["央企"]})
    rows.append({"name": "部分勾选硬过滤", "checks": [
        _check("仅央企 1 条", len(p["items"]) == 1 and p["items"][0]["company"] == "中石油",
               f"items={[x['company'] for x in p['items']]}"),
    ]})
    p = build({"company_types": ["央企"]}, {"company_types": ["国企"]})
    rows.append({"name": "前端∪画像并集", "checks": [
        _check("央企∪国企各 1 条", set(x["company"] for x in p["items"]) == {"中石油", "中国联通"},
               f"items={[x['company'] for x in p['items']]}"),
    ]})
    p = build({"company_types": ["未知"]})
    rows.append({"name": "非法类型全剔除", "checks": [
        _check("空清单不崩", len(p["items"]) == 0 and p["summary"]["total"] == 0,
               f"items={len(p['items'])}"),
    ]})
    p = build({}, {}, [])
    rows.append({"name": "空 match_results", "checks": [
        _check("空清单不崩", len(p["items"]) == 0 and p["summary"]["total"] == 0,
               f"items={len(p['items'])}"),
    ]})

    # ---- 阈值恰好 ----
    out = nodes.gate_match({"match_results": [{"score": 70}], "match_round": 0})
    rows.append({"name": "阈值边界 score==70", "checks": [
        _check("≥70 判定 pass", out["gate_verdict"] == "pass", f"verdict={out['gate_verdict']}"),
    ]})

    # ---- N9 未知 action（mock interrupt，避免误确认） ----
    with mock.patch("graph.nodes.interrupt", return_value={"action": "abort"}):
        out = nodes.confirm_resume({"config": {}, "user_approvals": {}, "match_results": [],
                                    "submission_plan": {"items": [], "status": "pending_review"}})
    rows.append({"name": "N9 未知 action", "checks": [
        _check("按 reject 处理", out["user_approvals"]["resume_final"] == "rejected",
               f"resume_final={out['user_approvals']['resume_final']}"),
        _check("原因含未知操作", "未知操作" in out["user_approvals"].get("reject_reason", ""),
               f"reason={out['user_approvals'].get('reject_reason')}"),
    ]})

    # ---- 导出渲染 ----
    from export.submission_html import render_submission_plan_html
    html_empty = render_submission_plan_html(build({}, {}, []), "line-mock", {})
    rows.append({"name": "导出·空清单", "checks": [
        _check("渲染不崩且含关键标记", "<!DOCTYPE html>" in html_empty and "投递清单" in html_empty,
               f"len={len(html_empty)}"),
    ]})
    dirty = [{"job_id": "x1", "title": "<b>岗位</b>", "company": '腾讯<&">X', "score": 90, "reasons": ["a&b"]}]
    html_dirty = render_submission_plan_html(build({}, {}, dirty), "line-mock", {})
    rows.append({"name": "导出·HTML 转义", "checks": [
        _check("原始标签/尖括号不出现", "<b>岗位</b>" not in html_dirty and "腾讯<&" not in html_dirty,
               f"len={len(html_dirty)}"),
        _check("转义实体存在", "&lt;b&gt;" in html_dirty, ""),
    ]})

    for r in rows:
        r["ok"] = all(c["ok"] for c in r["checks"])
    return rows


def run_node_boundary():
    """S10 节点级边界：构造缺字段 / 组件空返回的 state，断言各节点不崩且输出合理。
    覆盖：match_results 元素缺 score/title（gate/track/final_report）、组件链返回空数据
    （resume_generate/match_jobs/prep_materials/track_jobs 的 _run_* 挂点 patch）、
    补充信息非 list 不拆字符、路由未知 action 走 END。"""
    from graph.build import _route_confirm
    from unittest import mock

    def ok(name, cond, detail=""):
        return _check(name, cond, detail)

    rows = []

    # ---- 缺 score 元素 ----
    rows.append({"name": "缺 score 元素防御", "checks": [
        ok("gate_match 不崩", nodes.gate_match({"match_results": [{}]})["gate_verdict"]
           in ("pass", "fail", "accept_with_issues")),
        ok("track_jobs 不崩", isinstance(nodes.track_jobs({"match_results": [{}]})["tracking_records"], list)),
        ok("final_report 不崩", isinstance(nodes.final_report({"match_results": [{}]})["report"], dict)),
    ]})

    # ---- 组件链返回空数据（_run_* 挂点 patch → 节点 .get 兜底不崩） ----
    with mock.patch.object(nodes, "_run_resume_chain", return_value={}):
        out = nodes.resume_generate({"profile": {}})
    with mock.patch.object(nodes, "_run_match_chain", return_value={}):
        m_out = nodes.match_jobs({"profile": {}})
    with mock.patch.object(nodes, "_run_prep_chain", return_value={}):
        p_out = nodes.prep_materials({"resume": {}})
    with mock.patch.object(nodes, "_run_tracker", return_value=[]):
        t_out = nodes.track_jobs({"match_results": [], "user_input": {"tracking": []}})
    rows.append({"name": "组件链空返回防御", "checks": [
        ok("resume_generate 空 resume 不崩", out.get("resume", {}).get("round") == 1,
           f"resume={out.get('resume')}"),
        ok("match_jobs 空结果不崩", m_out["match_results"] == [], f"results={m_out['match_results']}"),
        ok("prep_materials 空材料不崩", p_out["interview_materials"].get("files") == [],
           f"materials={p_out['interview_materials']}"),
        ok("final_report 消费空材料不崩", isinstance(nodes.final_report(
            {"interview_materials": p_out["interview_materials"]})["report"], dict)),
        ok("track_jobs 空 records 不崩", t_out["tracking_records"] == [], f"records={t_out['tracking_records']}"),
    ]})

    # ---- 补充信息非 list 不拆字符 ----
    merged = nodes._merge_supplement({"skills": ["Python"]}, {"skills": "abc", "experience": "x"})
    rows.append({"name": "追问补充类型防御", "checks": [
        ok("字符串 skills 不拆字符", merged["skills"] == ["Python"], f"skills={merged['skills']}"),
        ok("非 list experience 忽略", "experience" not in merged, f"keys={list(merged.keys())}"),
    ]})

    # ---- N9 路由未知 action ----
    rows.append({"name": "N9 路由防御", "checks": [
        ok("未知 action 走 END", _route_confirm({"resume_decision": {"action": "abort"}}) == "END",
           f"route={_route_confirm({'resume_decision': {'action': 'abort'}})}"),
        ok("approve 走 prep", _route_confirm({"resume_decision": {"action": "approve"}}) == "prep_materials",
           f"route={_route_confirm({'resume_decision': {'action': 'approve'}})}"),
        ok("modify 回 N8", _route_confirm({"resume_decision": {"action": "modify"}}) == "resume_improve",
           f"route={_route_confirm({'resume_decision': {'action': 'modify'}})}"),
    ]})

    for r in rows:
        r["ok"] = all(c["ok"] for c in r["checks"])
    return rows


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------
def _fmt_state_key(final):
    ua = final.get("user_approvals", {})
    parts = {
        "简历轮次": final.get("resume_round"), "匹配轮次": final.get("match_round"),
        "判定": final.get("gate_verdict"), "定稿": ua.get("resume_final"),
        "缺失字段": final.get("missing_fields"), "错误数": len(final.get("errors", [])),
        "达标岗位": len(final.get("report", {}).get("matched", [])) if final.get("report") else None,
        "跟踪记录": len(final.get("tracking_records", [])),
    }
    return " ｜ ".join(f"{k}={v}" for k, v in parts.items() if v is not None)


def _interaction_desc(inter):
    p = inter["payload"]
    a = inter["answer"]
    if p["type"] == "ask_profile":
        missing = "、".join(p["missing_fields"])
        filled_skills = "、".join(a.get("skills", [])) or "无"
        filled_exp = "有" if a.get("experience") else "无"
        return f"追问(第{p['ask_round']+1}轮)·缺失[{missing}] → 用户补充技能[{filled_skills}]、经历[{filled_exp}]"
    if p["type"] == "confirm_resume":
        matched = len(p.get("matched", []))
        act = a.get("action")
        if act == "approve":
            return f"定稿确认·展示达标岗位{matched}个 → 用户「确认」"
        if act == "modify":
            return f"定稿确认·展示达标岗位{matched}个 → 用户「提修改」({a.get('feedback')})"
        if act == "reject":
            return f"定稿确认·展示达标岗位{matched}个 → 用户「拒绝」({a.get('reason')})"
    return f"{p['type']} → {a}"


def build_report(results, parse_rows, total_ok, export=None, q10_rows=None, s10_rows=None):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    add = lines.append
    add("# JOBHUNTER 大脑全链路测试报告（模拟用户各阶段输入）")
    add("")
    add(f"> 生成时间：{now} ｜ 运行模式：RUN_MODE=mock ｜ Python：{sys.version.split()[0]} ｜ langgraph：1.x")
    add(f"> 复现命令：`cd D:\\TRAE\\WORKSPACE\\JobHunter\\job-hunter-orchestrator && python run_full_e2e.py`")
    add("")
    add("## 一、测试范围与输入覆盖")
    add("")
    add("模拟用户在各个人工交互阶段的输入，覆盖三类维度：")
    add("- **输入方式**：一句话自然语言 / 半结构化（`方向：…；技能：…；经历：…`）")
    add("- **输入组合**：画像缺失→追问补充/放弃、N9 确认/修改/拒绝、skip_confirm、反馈环收敛/降级")
    add("- **输入内容**：不同方向（决策规划/感知/大模型/数据分析）、学历、技能栈、经历、城市、求职类型")
    add("")
    add("## 二、场景结果总表")
    add("")
    add("| 场景 | 说明 | 节点数 | 交互次数 | 最终判定 | 结果 |")
    add("|---|---|---|---|---|---|")
    for r in results:
        verdict = r["final"].get("gate_verdict") or "-"
        mark = "✅ 通过" if r["ok"] else "❌ 失败"
        add(f"| {r['id']} | {r['name']} | {len(r['path'])} | {len(r['interactions'])} | {verdict} | {mark} |")
    add(f"| S8 | 输入内容/方式变体解析（{len(parse_rows)} 组） | - | - | - | {'✅ 通过' if all(x['ok'] for x in parse_rows) else '❌ 失败'} |")
    add(f"")
    add(f"**汇总：全链路 {len(results)} 个场景 {'✅ 全部通过' if total_ok else '❌ 存在失败'}；解析变体 {'✅ 全部通过' if all(x['ok'] for x in parse_rows) else '❌ 存在失败'}**")
    add("")
    add("## 三、场景执行明细")
    add("")
    for r in results:
        add(f"### {r['id']} {r['name']}")
        add("")
        add(f"- 用户初始输入：`{r['goal']}`")
        if r["config"]:
            add(f"- 配置：`{r['config']}`")
        add(f"- 节点执行路径：`{' → '.join(r['path'])}`")
        add(f"- 耗时：{r['elapsed_ms']:.1f} ms")
        if r["interactions"]:
            add("- 用户交互（HITL）：")
            for inter in r["interactions"]:
                add(f"  - {_interaction_desc(inter)}")
        else:
            add("- 用户交互（HITL）：无（自动模式）")
        add(f"- 最终状态：{_fmt_state_key(r['final'])}")
        add("- 校验结果：")
        for c in r["checks"]:
            mark = "✅" if c["ok"] else "❌"
            detail = f"（{c['detail']}）" if c["detail"] else ""
            add(f"  - {mark} {c['name']}{detail}")
        add("")
    add("### S8 输入内容/方式变体解析")
    add("")
    add("| 变体 | 输入 | 画像抽取 | 校验 |")
    add("|---|---|---|---|")
    for x in parse_rows:
        prof = x["profile"]
        brief = (f"方向={prof['preference']['direction']}，技能={prof['skills']}，"
                 f"经历={len(prof['experience'])}条，类型={prof['preference']['type']}，城市={prof['preference']['city']}")
        mark = "✅" if x["ok"] else "❌"
        fails = "；".join(f"{c['name']}({c['detail']})" for c in x["checks"] if not c["ok"])
        add(f"| V{x['variant']} | `{x['goal']}` | {brief} | {mark} {fails} |")
    add("")
    add("## 四、结论与观察")
    add("")
    add(f"- 全链路场景 {len(results)} 个：" + ("全部通过" if total_ok else f"{sum(1 for r in results if r['ok'])}/{len(results)} 通过"))
    add("- 关键路径验证：完整画像首轮达标、画像缺失追问补充、反馈环收敛、轮次耗尽降级、N9 三种用户决定（确认/修改/拒绝）、skip_confirm 自动模式均已覆盖")
    add("- 风险点：mock 模式下匹配分由「技能-JD 关键词重叠」驱动，真实模式需接入 JS-Agent 混合判定；追问与定稿确认当前用 `interrupt()` + MemorySaver，接入真实前端/数据库持久化时需换持久化 Checkpointer")
    add("")
    add("## 五、投递清单导出（Q10e）")
    add("")
    if export is None:
        add("- 导出 smoke：未执行")
    else:
        mark = "✅ 通过" if export["ok"] else "❌ 失败"
        add(f"- 导出 smoke：{mark}（复用范本格式：A4 横向 / hero 页眉 / tier 分组表格 / sources 来源双栏）")
        for c in export["checks"]:
            m = "✅" if c["ok"] else "❌"
            d = f"（{c['detail']}）" if c["detail"] else ""
            add(f"  - {m} {c['name']}{d}")
        if export.get("out"):
            add(f"- 示例文件：`{export['out']}`")
    if q10_rows is not None:
        add("")
        add("## 六、Q10 边界校验（S9）")
        add("")
        ok_all = all(r["ok"] for r in q10_rows)
        add(f"- 边界组 {len(q10_rows)} 个：" + ("全部通过" if ok_all else f"{sum(1 for r in q10_rows if r['ok'])}/{len(q10_rows)} 通过"))
        for r in q10_rows:
            mark = "✅" if r["ok"] else "❌"
            add(f"- {mark} {r['name']}")
            for c in r["checks"]:
                m = "✅" if c["ok"] else "❌"
                d = f"（{c['detail']}）" if c["detail"] else ""
                add(f"  - {m} {c['name']}{d}")
    if s10_rows is not None:
        add("")
        add("## 七、节点级边界（S10）")
        add("")
        ok_all = all(r["ok"] for r in s10_rows)
        add(f"- 节点边界组 {len(s10_rows)} 个：" + ("全部通过" if ok_all else f"{sum(1 for r in s10_rows if r['ok'])}/{len(s10_rows)} 通过"))
        for r in s10_rows:
            mark = "✅" if r["ok"] else "❌"
            add(f"- {mark} {r['name']}")
            for c in r["checks"]:
                m = "✅" if c["ok"] else "❌"
                d = f"（{c['detail']}）" if c["detail"] else ""
                add(f"  - {m} {c['name']}{d}")
    return "\n".join(lines) + "\n"


def main():
    # 打开 Q10/N9 投递确认链路日志（LEVEL=INFO 起可看到埋点，排查时可用 DEBUG 查看更多）
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    results = []
    for sc in SCENARIOS:
        results.append(run_scenario(sc))
    parse_rows = run_parse_variants()
    export = run_export_smoke(results)
    q10_rows = run_q10_boundary()
    s10_rows = run_node_boundary()
    total_ok = (all(r["ok"] for r in results) and all(x["ok"] for x in parse_rows)
                and export["ok"] and all(r["ok"] for r in q10_rows)
                and all(r["ok"] for r in s10_rows))

    report = build_report(results, parse_rows, total_ok, export, q10_rows, s10_rows)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.datetime.now().strftime("%Y%m%d")
    out = REPORT_DIR / f"大脑全链路测试报告-{date}.md"
    out.write_text(report, encoding="utf-8")

    # 控制台摘要
    print(f"=== JOBHUNTER 大脑全链路测试 ===")
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"[{mark}] {r['id']} {r['name']}  nodes={len(r['path'])}  interacts={len(r['interactions'])}  {r['elapsed_ms']:.1f}ms")
    print(f"[{'PASS' if all(x['ok'] for x in parse_rows) else 'FAIL'}] S8 输入变体解析 x{len(parse_rows)}")
    print(f"[{'PASS' if export['ok'] else 'FAIL'}] Q10e 投递清单导出 smoke"
          + (f"  -> {export['out']}" if export.get("out") else ""))
    print(f"[{'PASS' if all(r['ok'] for r in q10_rows) else 'FAIL'}] S9 Q10 边界校验 x{len(q10_rows)}")
    print(f"[{'PASS' if all(r['ok'] for r in s10_rows) else 'FAIL'}] S10 节点级边界 x{len(s10_rows)}")
    print(f"报告已生成：{out}")


if __name__ == "__main__":
    main()
