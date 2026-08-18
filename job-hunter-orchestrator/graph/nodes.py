"""大脑节点实现（M4 · 组件化主线版：mock 离线可跑，real 进程内组件 + LLM）

每个节点 = 一个纯函数(state) -> dict(增量更新 state)
能力来源（独立单项目模型，2026-08-18）：
- 三组件（components/resume_agent · match_agent · prep_agent）= 能力主线，进程内调用；
- 进程内 LLM（clients/llm.py，OpenAI 兼容直连）解析画像 / 差距分析；
- 组件异常 → 节点内确定性降级（骨架简历 / 规则匹配 / 预置材料），不依赖任何外部服务；
- tracker = 本地 JSON 存储组件（components/tracker_agent）。
"""
import asyncio
import datetime
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Dict

from langgraph.types import interrupt
from graph.state import JobHunterState

logger = logging.getLogger("jobhunter.graph")  # 统一日志：宿主（测试/服务）负责 basicConfig 级别

# ---------- 常量（对应设计文档 §5） ----------
MATCH_PASS_THRESHOLD = 70      # 匹配达标分数
MAX_MATCH_ROUNDS = 3           # 反馈环轮数上限
MAX_FEEDBACK_ITEMS = 5         # 差距建议条数上限
MAX_PROFILE_RETRIES = 2        # 画像追问轮数上限（N2 interrupt）

# Q10 投递清单（对齐《投递清单生成设计.md》§3.4 枚举，企业类型 6 类含外企）
COMPANY_TYPES_ALL = ["央企", "国企", "大型", "中型", "小型", "外企"]
DEFAULT_MAX_RESULTS = 20
MAX_MAX_RESULTS = 200          # 防御性上限：防超大切片 / 超量清单

# 模块级加载项目根 .env 到进程环境（RUN_MODE / LLM_* 即时生效，无需额外 dotenv 依赖；
# setdefault 保证不覆盖用户显式设置的环境变量；.env 缺失/解析失败不影响启动）
try:
    from clients.llm import _read_env as _load_env
    for _k, _v in _load_env().items():
        os.environ.setdefault(_k, _v)
except Exception:  # noqa: BLE001
    pass

RUN_MODE = os.getenv("RUN_MODE", "mock")


# ---------- 组件化主线（M4）：components/ 进程内接入 ----------
_COMPONENTS_DIR = Path(__file__).resolve().parent.parent.parent / "components"
if str(_COMPONENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_COMPONENTS_DIR))


def _read_env() -> Dict[str, str]:
    """读取项目根 .env（与 clients/llm.py 同一套解析，控制台 Key 即时生效）。"""
    from clients.llm import _read_env as _llm_read_env
    return _llm_read_env()


def _llm_call(system: str, user: str, provider_id: str | None = None,
              model: str | None = None, **kwargs) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """clients/llm.py chat_json 适配组件 (obj, meta) 注入协议（decide/evaluate/judge）。"""
    from clients.llm import chat_json
    obj = chat_json(system, user, **kwargs)
    return obj, {"backend": "real", "model": model or "env"}


def _run_async(coro):
    """同步节点内执行 async 组件链（宿主均为同步 invoke，无运行中事件循环）。
    防御：若未来 async 宿主，起独立线程桥接（fresh loop）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    result: dict[str, Any] = {}

    def _worker() -> None:
        result["value"] = asyncio.run(coro)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join()
    return result["value"]


# 组件链懒加载单例（real 注入 LLM / mock 注入确定性后端）
_RESUME_CHAIN: Any = None
_PREP_CHAIN: Any = None
_TRACKER_STORE: Any = None


def _llm_key() -> str:
    key = (_read_env().get("LLM_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("未配置 API Key（LLM_API_KEY），real 模式拒绝服务")
    return key


def _resume_provider():
    """real：按大脑 .env（LLM_* 四项）构造 lib LLMProvider，保持单一 Key 配置 UX。"""
    from app.config import Config, ProviderCfg  # resume_agent/lib
    from app.core.providers import LLMProvider
    env = _read_env()
    os.environ["__JOBHUNTER_LLM_KEY__"] = _llm_key()
    cfg = Config()
    cfg.provider = ProviderCfg(
        base_url=(env.get("LLM_BASE_URL") or os.getenv("LLM_BASE_URL")
                  or "https://api.deepseek.com").rstrip("/"),
        api_key_env="__JOBHUNTER_LLM_KEY__",
        model=(env.get("LLM_MODEL") or os.getenv("LLM_MODEL") or "deepseek-v4-flash"),
    )
    return LLMProvider(cfg)


def _resume_chain():
    global _RESUME_CHAIN
    if _RESUME_CHAIN is None:
        from resume_agent import build_resume_chain
        from resume_agent.mock_provider import MockLLMProvider
        provider = MockLLMProvider() if RUN_MODE == "mock" else _resume_provider()
        _RESUME_CHAIN = build_resume_chain(provider=provider)
    return _RESUME_CHAIN


def _prep_client():
    from prep_agent.llm import LLMClient
    if RUN_MODE == "mock":
        return LLMClient(backend="mock")
    env = _read_env()
    return LLMClient(
        backend="real", api_key=_llm_key(),
        model=(env.get("LLM_MODEL") or os.getenv("LLM_MODEL") or "deepseek-v4-flash"),
        base_url=(env.get("LLM_BASE_URL") or os.getenv("LLM_BASE_URL")
                  or "https://api.deepseek.com"),
    )


def _prep_chain():
    global _PREP_CHAIN
    if _PREP_CHAIN is None:
        from prep_agent import build_prep_chain
        _PREP_CHAIN = build_prep_chain(client=_prep_client())
    return _PREP_CHAIN


def _match_chain(target_jobs: list) -> Any:
    """按 RUN_MODE 构造 match_agent 链：mock 注入目标岗位驱动的搜索后端。"""
    from match_agent import build_match_chain
    if RUN_MODE == "real":
        return build_match_chain(backend="real", llm_call=_llm_call)
    from graph.mock_backend import GoalMockSearchBackend
    return build_match_chain(backend="mock",
                             search_chain=GoalMockSearchBackend(target_jobs))


def _tracker():
    global _TRACKER_STORE
    if _TRACKER_STORE is None:
        from tracker_agent import TrackerStore
        _TRACKER_STORE = TrackerStore()
    return _TRACKER_STORE


# 组件执行入口（节点调用 / 测试 patch 的统一挂点）
def _run_resume_chain(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return _run_async(_resume_chain().ainvoke(inputs))


def _run_match_chain(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return _match_chain(inputs.get("target_jobs") or []).invoke(inputs)


def _run_prep_chain(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return _run_async(_prep_chain().ainvoke(inputs))


def _run_tracker(records: list) -> list:
    return _tracker().append(records)


# ---------- N1 画像解析 ----------
# mock 解析用的词表与岗位模板（真实版：LLM 抽取；测试通过不同 user_goal 验证解析差异）
_DIRECTIONS = ["决策规划", "感知", "大模型", "数据分析", "机器学习"]
_SKILL_WORDS = ["Python", "C++", "PyTorch", "深度学习", "机器学习", "大模型", "LLM",
                "Agent", "RAG", "SQL", "数据分析", "NLP", "目标检测", "轨迹预测",
                "决策规划", "感知", "ROS", "Java"]
_CITIES = ["北京", "上海", "深圳", "广州", "杭州", "成都", "南京", "武汉", "西安"]

_DIRECTION_JOBS: Dict[str, list] = {
    "决策规划": [
        {"title": "自动驾驶决策规划实习生", "company": "示例公司A",
         "jd": "熟悉决策规划算法，掌握C++/Python，有轨迹预测经验优先"},
        {"title": "自动驾驶算法实习生", "company": "示例公司B",
         "jd": "熟悉深度学习，有感知或规划项目经验"},
    ],
    "感知": [
        {"title": "自动驾驶感知算法实习生", "company": "示例公司B",
         "jd": "熟悉深度学习，有目标检测或感知项目经验，掌握Python/PyTorch"},
    ],
    "大模型": [
        {"title": "大模型应用开发实习生", "company": "示例公司C",
         "jd": "熟悉大模型应用开发，掌握Prompt/Agent/RAG，会Python，有LLM项目经验优先"},
    ],
    "数据分析": [
        {"title": "数据分析实习生", "company": "示例公司D",
         "jd": "熟悉SQL与Python数据分析，有统计建模与可视化经验"},
    ],
    "机器学习": [
        {"title": "机器学习算法实习生", "company": "示例公司E",
         "jd": "熟悉机器学习/深度学习，掌握Python与PyTorch"},
    ],
}
_DEFAULT_JOBS = _DIRECTION_JOBS["决策规划"]


def _parse_goal_mock(goal: str) -> tuple[Dict[str, Any], list]:
    """规则版画像抽取：从用户一句话提取 类型/方向/技能/经历/城市/背景。
    供全链路测试模拟不同 user_goal 输入；真实版由 LLM 完成。"""
    gl = goal.lower()
    # 求职类型
    wtype = "实习"
    for kw in ["秋招", "校招", "应届"]:
        if kw in goal:
            wtype = "秋招"
            break
    # 方向
    direction = next((d for d in _DIRECTIONS if d in goal), None)
    # 技能（去重保序）
    skills: list = []
    for s in _SKILL_WORDS:
        if s.lower() in gl and s not in skills:
            skills.append(s)
    # 经历（提取"做过/参与/负责/完成 XX"）
    experience: list = []
    for kw in ("做过", "参与", "负责", "完成"):
        idx = goal.find(kw)
        if idx >= 0:
            m = re.match(r"([\u4e00-\u9fa5A-Za-z0-9+]{2,12})", goal[idx + len(kw):])
            if m:
                name = m.group(1)
                name = name if name.endswith(("项目", "课题")) else name + "项目"
                experience.append({"name": name, "desc": goal.strip()[:60]})
                break
    # 城市
    city = next((c for c in _CITIES if c in goal), "不限")
    # 背景
    if "博士" in goal:
        bg = "博士在读"
    elif "硕士" in goal:
        bg = "硕士在读"
    elif "本科" in goal:
        bg = "本科在读"
    else:
        bg = "求职者"
    profile = {
        "background": bg,
        "skills": skills,
        "experience": experience,
        "preference": {"city": city, "direction": direction or "不限", "type": wtype},
    }
    jobs = _DIRECTION_JOBS.get(direction) or list(_DEFAULT_JOBS)
    return profile, jobs


PROFILE_SYSTEM = (
    "你是求职画像解析器。从用户一句话求职诉求中抽取结构化画像，输出严格 JSON：\n"
    '{"background":"学历/身份（如 硕士在读）","skills":["技能名"],'
    '"experience":[{"name":"项目/经历名","desc":"一句话简述"}],'
    '"preference":{"city":"城市","direction":"岗位方向","type":"实习|秋招"},'
    '"degree":"最高学历","target_jobs":[{"title":"意向岗位","company":""}]}\n'
    "要求：只抽取用户明确提到的信息，未提到的字段填空字符串/空数组，严禁编造。"
)


def parse_profile(state: JobHunterState) -> Dict[str, Any]:
    """画像获取：前端表单已传结构化 profile → 直接采用；否则 LLM/规则解析 user_goal。"""
    existing = state.get("profile") or {}
    if existing.get("skills") or existing.get("experience"):
        # 前端已收集完整画像（表单/简历版本），不再用 user_goal 覆盖（避免 N2 误判缺失）
        return {"profile": existing, "target_jobs": state.get("target_jobs", [])}
    goal = (state.get("user_goal") or "").strip()
    if RUN_MODE == "real" and goal:
        try:
            obj, _ = _llm_call(PROFILE_SYSTEM, goal)
            profile = {
                "background": obj.get("background", ""),
                "skills": [str(s) for s in (obj.get("skills") or []) if str(s).strip()],
                "experience": list(obj.get("experience") or []),
                "preference": obj.get("preference") or {},
                "degree": obj.get("degree", ""),
            }
            jobs = list(obj.get("target_jobs") or [])
            if profile.get("skills") or profile.get("experience"):
                logger.info("N1 画像解析 真实 LLM: 技能=%d 经历=%d 岗位=%d",
                            len(profile["skills"]), len(profile["experience"]), len(jobs))
                return {"profile": profile, "target_jobs": jobs}
        except Exception as exc:  # noqa: BLE001  无 Key/网络/非 JSON → 降级规则解析
            logger.warning("N1 LLM 解析失败，降级规则解析: %s", exc)
    if not goal:
        # 兼容：无输入时用示例画像
        profile, jobs = _parse_goal_mock("硕士在读，做过自动驾驶感知项目，找实习，方向是决策规划")
        return {"profile": profile, "target_jobs": jobs}
    profile, jobs = _parse_goal_mock(goal)
    return {"profile": profile, "target_jobs": jobs}


def _missing_fields(profile: Dict[str, Any]) -> list:
    missing = []
    if not profile.get("skills"):
        missing.append("skills")
    if not profile.get("experience"):
        missing.append("experience")
    return missing


def _merge_supplement(profile: Dict[str, Any], answers: Dict[str, Any]) -> Dict[str, Any]:
    """用户补充信息合并进画像（N1B 追问回填）"""
    profile = dict(profile)
    # 仅接受非空 list/dict 合并，防御异常输入（如字符串被 list() 拆成字符污染画像）
    if isinstance(answers.get("skills"), list) and answers["skills"]:
        profile["skills"] = list(answers["skills"])
    if isinstance(answers.get("experience"), list) and answers["experience"]:
        profile["experience"] = list(answers["experience"])
    if isinstance(answers.get("preference"), dict) and answers["preference"]:
        profile["preference"] = {**profile.get("preference", {}), **answers["preference"]}
    return profile


# ---------- N2 画像完整性检查（条件节点） ----------
def check_profile(state: JobHunterState) -> Dict[str, Any]:
    """规则检查必填字段；缺失且未达追问上限 → interrupt 追问用户补充（合并进画像）。
    本节点每次执行至多 interrupt 一次；仍缺失时由 build.py 回环本节点继续追问（≤2 轮）。"""
    profile = state.get("profile", {})
    missing = _missing_fields(profile)
    ask_round = state.get("profile_ask_round", 0)
    approvals = dict(state.get("user_approvals", {}))
    if missing and ask_round < MAX_PROFILE_RETRIES:
        answers = interrupt({
            "type": "ask_profile",
            "missing_fields": missing,
            "ask_round": ask_round,
            "hint": "请补充缺失字段后再继续",
        })
        profile = _merge_supplement(profile, answers or {})
        missing = _missing_fields(profile)
        ask_round += 1
    approvals["profile_ok"] = not missing
    return {"profile": profile, "missing_fields": missing,
            "profile_ask_round": ask_round, "user_approvals": approvals}


# ---------- N3 简历生成 ----------
_DEGREE_MAP = {"本科": "学士", "学士": "学士", "硕士": "硕士", "博士": "博士",
               "大专": "专科", "专科": "专科"}


def _grad_year(text: str) -> int | None:
    m = re.search(r"(20\d{2})", text or "")
    return int(m.group(1)) if m else None


def _month_range(text: str) -> tuple | None:
    """从自由时间文本提取 (start, end) 月份对（YYYY.MM），无法解析返回 None。"""
    m = re.findall(r"(20\d{2})[.\-/年](\d{1,2})", text or "")
    if len(m) >= 2:
        return (f"{m[0][0]}.{int(m[0][1]):02d}", f"{m[1][0]}.{int(m[1][1]):02d}")
    return None


def _edu_items(profile: Dict[str, Any]) -> list:
    """教育经历 → resume_agent Education 结构（字段强校验：degree 枚举 + 起止月份，
    不合规的条目跳过，避免组件整体校验失败降级为骨架）。"""
    items = []
    for e in (profile.get("education") or []):
        school = str(e.get("school") or "").strip()
        major = str(e.get("major") or "").strip()
        degree = _DEGREE_MAP.get(str(e.get("degree") or "").strip(), "")
        year = _grad_year(str(e.get("year") or ""))
        if not (school and major and degree and year):
            continue
        items.append({"school": school[:64], "major": major[:64], "degree": degree,
                      "startMonth": f"{year - 3}.09", "endMonth": f"{year}.06"})
    return items[:3]


def _int_items(profile: Dict[str, Any]) -> list:
    """实习经历 → Internship 结构（起止月份可解析才入列；duties 由组件润色生成）。"""
    items = []
    for it in (profile.get("internships") or []):
        company = str(it.get("company") or "").strip()
        position = str(it.get("position") or "").strip()
        rng = _month_range(str(it.get("time") or ""))
        if not (company and position and rng):
            continue
        items.append({"company": company[:64], "position": position[:64],
                      "startMonth": rng[0], "endMonth": rng[1],
                      "overview": str(it.get("desc") or "")[:300], "duties": []})
    return items[:2]


def _skeleton_resume(profile: Dict[str, Any], target_jobs: list,
                     feedback: list) -> Dict[str, Any]:
    """画像 → resume_agent 输入骨架（完整透传姓名/联系方式/教育/实习/项目/奖项，
    缺失或不合规字段跳过，保证组件强校验不失败）。"""
    direction = (profile.get("preference") or {}).get("direction") or "AI"
    city = (profile.get("preference") or {}).get("city") or ""
    skills = [{"name": s} if isinstance(s, str) else s
              for s in (profile.get("skills") or [])]
    projects = []
    for e in (profile.get("experience") or []):
        name = (e.get("name") if isinstance(e, dict) else str(e)) or "未命名项目"
        rng = _month_range(str(e.get("time") or ""))
        desc = str(e.get("desc") or "").strip()
        projects.append({
            "name": str(name)[:64], "role": str(e.get("role") or "")[:32],
            "startMonth": rng[0] if rng else None, "endMonth": rng[1] if rng else None,
            "techStack": [s for s in re.split(r"[、,，;；\s]+", str(e.get("stack") or "")) if s][:8],
            "items": [{"text": desc[:500], "criticality": "medium"}] if desc else [],
            "source": "user-input", "aiFlag": False,
        })
    honors = [{"name": str(a).strip()[:128]} for a in (profile.get("awards") or [])
              if str(a).strip()]
    return {
        "direction": direction,
        "resume": {
            "id": "jobhunter", "identity": "intern", "pageOption": "one-page",
            "basicInfo": {"name": str(profile.get("name") or "求职者")[:32],
                          "age": 22,
                          "email": str(profile.get("email") or "") or "jobhunter@local",
                          "phone": str(profile.get("phone") or "") or "00000000000",
                          "website": str(profile.get("website") or "").strip() or None,
                          "base": city or None},
            "education": _edu_items(profile),
            "internship": _int_items(profile),
            "skill": skills, "project": projects, "honor": honors,
            "generation": {"deepSearch": False}, "contentPlan": {},
            "feedback_hint": f"已按建议改进（{len(feedback)} 条）" if feedback else "",
        },
        "jobs": [
            {"id": f"job-{i}", "title": j.get("title", ""), "jdText": j.get("jd", ""),
             "domainTags": []}
            for i, j in enumerate(target_jobs)
        ],
    }


def resume_generate(state: JobHunterState) -> Dict[str, Any]:
    """进程内 resume_agent 链生成简历（携带 resume_feedback 改进，审核回路随组件携带）。
    组件异常 → 降级为骨架简历（确定性，无外部服务依赖）。"""
    profile = state.get("profile", {})
    target_jobs = state.get("target_jobs", [])
    feedback = state.get("resume_feedback", [])
    try:
        out = _run_resume_chain(_skeleton_resume(profile, target_jobs, feedback))
    except Exception as exc:  # noqa: BLE001
        logger.warning("N3 resume_agent 组件异常，降级骨架简历: %s", exc)
        skeleton = _skeleton_resume(profile, target_jobs, feedback)["resume"]
        skeleton["round"] = state.get("resume_round", 0) + 1
        return {"resume": skeleton, "resume_round": state.get("resume_round", 0) + 1,
                "errors": state.get("errors", []) + [f"resume_agent 组件降级：{exc}"]}
    resume = out.get("resume") or {}
    review = out.get("review_results")
    resume["round"] = state.get("resume_round", 0) + 1
    # 模板装配 html（专业 ATS 版式）随 resume 下发，前端预览优先渲染该 html
    html = out.get("html")
    if html:
        resume["html"] = html
    out_state: Dict[str, Any] = {"resume": resume,
                                 "resume_round": state.get("resume_round", 0) + 1}
    # 审核结果（resume_agent 组件 review_results）写入 state，供 N7/N11 消费
    if review:
        out_state["review_results"] = review
    return out_state


# ---------- N4 岗位匹配 ----------
def _fallback_match(profile: Dict[str, Any], resume: Dict[str, Any],
                    target_jobs: list, rnd: int) -> list:
    """组件降级：输入驱动规则评分（技能-JD 关键词重叠，确定性、无外部服务依赖）。
    分值 = 45 + 命中*10 + 轮次*5 - 岗位序*4（封顶 99）；命中≥3 首轮达标、=2 二轮、≤1 三轮降级。"""
    skills = {str(s).lower() for src in (profile.get("skills", []), resume.get("skills", []))
              for s in (src or [])}
    results = []
    for i, j in enumerate(target_jobs):
        jd = (j.get("jd") or "").lower()
        hit = sum(1 for s in skills if s and s in jd)
        score = min(99, 45 + hit * 10 + rnd * 5 - i * 4)
        results.append({
            "job_id": f"job-{i}",
            "title": j.get("title", ""),
            "company": j.get("company", ""),
            "score": score,
            "reasons": (["技能栈匹配度高", "方向契合"] if hit >= 3
                        else (["部分技能契合"] if hit >= 1 else ["技能栈不匹配"])),
            "resume_tips": ([{"tip": "补充JD关键词可提升匹配分"}] if hit < 3 else []),
        })
    return results


def match_jobs(state: JobHunterState) -> Dict[str, Any]:
    """进程内 match_agent 链匹配（搜索回路 + 混合判定，返回 score+reasons+gap_summary）。
    组件异常 → 降级为内部规则匹配（确定性，无外部服务依赖）。"""
    profile = state.get("profile", {})
    resume = state.get("resume", {})
    target_jobs = state.get("target_jobs", [])
    inputs = {
        "profile": profile,
        "resume": resume,
        "target_jobs": target_jobs,
        "resumeVer": (resume.get("line") or "line-mock"),
    }
    try:
        out = _run_match_chain(inputs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("N4 match_agent 组件异常，降级规则匹配: %s", exc)
        return {"match_results": _fallback_match(profile, resume, target_jobs,
                                                 state.get("match_round", 0)),
                "errors": state.get("errors", []) + [f"match_agent 组件降级：{exc}"]}
    results = out.get("match_results") or []
    # 组件返回空结果（真实搜索后端全不可达/被反爬/超时，无异常可捕获）→ 节点内规则降级，
    # 保证 N9 始终有达标岗位与投递清单，不因外部搜索不可用而产出空清单
    if not results and target_jobs:
        logger.warning("N4 match_agent 返回空结果（%d 个目标岗位），降级规则匹配",
                       len(target_jobs))
        return {"match_results": _fallback_match(profile, resume, target_jobs,
                                                 state.get("match_round", 0)),
                "gap_summary": out.get("gap_summary") or {},
                "errors": state.get("errors", []) + ["match_agent 空结果降级：真实搜索后端未返回岗位"]}
    logger.info("N4 匹配完成: 候选=%d", len(results))
    return {"match_results": results,
            "gap_summary": out.get("gap_summary") or {}}


# ---------- N5 匹配质量判定（条件节点） ----------
def gate_match(state: JobHunterState) -> Dict[str, Any]:
    """混合判定：规则层(最高分≥阈值) + LLM层(语义可信度，骨架版跳过)
    返回 gate_verdict + route，路由由 build.py 条件边决定"""
    results = state.get("match_results", [])
    top = max((r.get("score", 0) for r in results), default=0)
    rnd = state.get("match_round", 0)
    if top >= MATCH_PASS_THRESHOLD:
        verdict = "pass"
    elif rnd < MAX_MATCH_ROUNDS - 1:
        verdict = "fail"
    else:
        verdict = "accept_with_issues"
    return {
        "gate_verdict": verdict,
        "gap_summary": "" if verdict == "pass" else f"最高分 {top} < {MATCH_PASS_THRESHOLD}",
    }


# ---------- Q10 投递清单生成（2026-08-18 落地） ----------
def _enterprise_type_of(company: str) -> str:
    """mock：按公司名关键字推断企业类型（真实版：JS-Agent enterprise classifier，返回 6 值含「未知」）。
    骨架示例公司无分类信息 → 默认「大型」；无法判定 → 「未知」（选了类型时会被过滤）。"""
    c = (company or "").lower()
    kws = {
        "央企": ["中石油", "中石化", "国家电网", "中国移动", "中国银行", "工商银行", "华润", "中核", "中航", "招商局"],
        "国企": ["中国联通", "中国电信", "南方电网", "比亚迪"],
        "大型": ["腾讯", "阿里", "华为", "字节", "百度", "美团", "京东", "网易", "小米", "拼多多", "快手",
                 "商汤", "科大讯飞", "大疆", "影石", "万兴", "优必选", "平安", "微保"],
        "中型": ["元戎", "小鹏", "智元", "第四范式", "创维", "富士康", "招银"],
        "小型": ["戴盟", "聆海", "盈达", "清程", "道通", "丰图", "星尘", "iData", "TCL 工业"],
        "外企": ["特斯拉", "微软", "谷歌", "英伟达", "甲骨文", "三星", "intel", "amd", "西门子"],
    }
    for t, words in kws.items():
        if any(w in c for w in words):
            return t
    return "大型"


def build_submission_plan(state: JobHunterState) -> Dict[str, Any]:
    """Q10 投递清单生成（大脑节点，只推荐不引导）：
    消费四项输入（简历解析 profile + city + max_results + company_types，设计 §2.2）
    → 候选（复用 N4 match_results）→ 企业类型过滤 → 排序截断 → 分档 → 理由 → 汇总。
    骨架版全规则确定性执行；LLM 仅真实版润色理由（异常降级为 reasons 摘要，不阻塞）。
    清单状态 pending_review，由 N9 投递确认时置 confirmed。"""
    results = state.get("match_results", [])
    profile = state.get("profile", {})
    resume = state.get("resume", {})
    inp = state.get("submission_input") or {}

    # 四项输入（前端/测试显式传入优先，缺省用画像与默认值）
    city = inp.get("city") or (profile.get("preference") or {}).get("city") or "不限"
    # max_results 防御解析：缺失/文本/0/负数 → 默认 20；超大（>MAX）→ 上限截断
    # （负数若不拦截，切片 candidates[:-n] 会从末尾截断，条数错乱甚至空清单）
    raw_mr = inp.get("max_results")
    try:
        max_results = int(raw_mr) if raw_mr is not None else DEFAULT_MAX_RESULTS
    except (TypeError, ValueError):
        max_results = DEFAULT_MAX_RESULTS
    if max_results < 1:
        logger.warning("Q10 max_results=%r 非法，降级为默认 %d", raw_mr, DEFAULT_MAX_RESULTS)
        max_results = DEFAULT_MAX_RESULTS
    elif max_results > MAX_MAX_RESULTS:
        logger.warning("Q10 max_results=%s 超上限，截断为 %d", max_results, MAX_MAX_RESULTS)
        max_results = MAX_MAX_RESULTS
    frontend_types = list(inp.get("company_types") or [])
    profile_types = list(profile.get("company_types") or [])
    logger.info("Q10 投递清单生成 进入: match_round=%s 候选=%d city=%s max_results=%s company_types(前端)=%s company_types(画像)=%s",
                state.get("match_round"), len(results), city, max_results, frontend_types, profile_types)
    # 过滤集合 = 前端勾选 ∪ 画像推断（去重保序）；覆盖全部 6 类 → 归一化为不限
    selected = list(dict.fromkeys([*frontend_types, *profile_types]))
    if selected and set(selected) >= set(COMPANY_TYPES_ALL):
        selected = []
    logger.info("Q10 企业类型过滤集合: selected=%s", selected or "不限(未过滤)")

    # 企业类型过滤：selected 为空（全不勾 + 画像未声明）→ 不限；否则严格过滤（含「未知」）
    candidates = []
    for r in results:
        etype = _enterprise_type_of(r.get("company", ""))
        if selected and etype not in selected:
            continue
        candidates.append({**r, "enterprise_type": etype})
    if len(candidates) != len(results):
        logger.info("Q10 企业类型过滤: 剔除 %d/%d 条（类型不在所选范围，含「未知」）",
                    len(results) - len(candidates), len(results))

    # 排序：final_score 降序（同分保持原序）；截断 ≤ max_results
    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    if len(candidates) > max_results:
        logger.info("Q10 排序截断: %d → 前 %d 条", len(candidates), max_results)
    candidates = candidates[:max_results]

    items = []
    for i, r in enumerate(candidates, 1):
        score = r.get("score", 0)
        tier = "P0" if score >= 90 else ("P1" if score >= 80 else "P2")
        reasons = list(r.get("reasons", []) or [])
        items.append({
            "job_id": r.get("job_id", f"job-{i}"),
            "title": r.get("title", ""),
            "company": r.get("company", ""),
            "city": city,
            "channel": "招聘平台",  # 骨架版默认；真实版由搜索回路提供（招聘平台/官网/社区）
            "source_url": r.get("source_url") or f"https://example.com/job/{r.get('job_id', i)}",
            "final_score": score,
            "enterprise_type": r.get("enterprise_type", "大型"),
            "resumeVer": resume.get("line") or "line-mock",
            "tier": tier,
            "reason": "；".join(reasons) or "规则匹配",
            "reasons": reasons,
            "user_action": "suggested",  # 用户参考标注，不驱动投递（设计 §3.5）
            "applied_at": None,
        })

    channels = sorted({x["channel"] for x in items})
    versions = sorted({x["resumeVer"] for x in items})
    # N9 弹窗按档位分组展示：tiers[{name, jobs[{title, company, score}]}] + 顶层 total
    # （前端 confirmResume 读取此结构；items/summary 保留供投递清单板块与导出使用）
    tiers = [
        {"name": tier, "jobs": [
            {"title": x["title"], "company": x["company"], "score": x["final_score"]}
            for x in items if x["tier"] == tier
        ]}
        for tier in ("P0", "P1", "P2") if any(x["tier"] == tier for x in items)
    ]
    plan = {
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "status": "pending_review",  # pending_review → confirmed（N9 确认）
        "total": len(items),
        "tiers": tiers,
        "items": items,
        "summary": {
            "total": len(items),
            "by_tier": {t: sum(1 for x in items if x["tier"] == t) for t in ("P0", "P1", "P2")},
            "by_channel": {c: sum(1 for x in items if x["channel"] == c) for c in channels},
            "by_resumeVer": {v: sum(1 for x in items if x["resumeVer"] == v) for v in versions},
        },
        "filters": {"city": city, "max_results": max_results,
                    "company_types": selected or "不限"},
    }
    logger.info("Q10 投递清单生成 完成: items=%d by_tier=%s status=pending_review",
                len(items), {t: sum(1 for x in items if x["tier"] == t) for t in ("P0", "P1", "P2")})
    return {"submission_plan": plan}


# ---------- N7 差距分析 ----------
GAP_SYSTEM = (
    "你是求职差距分析器。对比目标岗位 JD 与用户简历，找出可补足的能力差距，输出严格 JSON：\n"
    '{"feedback":[{"gap":"差距描述","suggestion":"改进建议","priority":"high|mid|low"}]}\n'
    "要求：只基于给出的 JD 与简历信息，严禁编造经历；最多 5 条。"
)


def _gap_prompt(jd: str, resume: Dict[str, Any]) -> str:
    """序列化 JD + 简历（摘要）供 LLM 差距分析。"""
    def _flat(items: list) -> str:
        parts = []
        for it in items or []:
            if isinstance(it, str):
                parts.append(it)
            elif isinstance(it, dict):
                name = it.get("name") or it.get("title") or it.get("text") or ""
                detail = it.get("desc") or it.get("detail") or ""
                parts.append(f"{name}：{detail}".strip("："))
        return "；".join(parts)

    r = resume or {}
    return (
        f"【目标岗位 JD】\n{jd}\n\n"
        f"【用户简历摘要】\n"
        f"技能：{'、'.join(str(s.get('name', s)) for s in (r.get('skill') or []) if s)}\n"
        f"项目：{_flat(r.get('project'))}\n"
        f"实习：{_flat(r.get('internship'))}\n"
    )


def gap_analysis(state: JobHunterState) -> Dict[str, Any]:
    """LLM：对比最高分岗位 JD 与简历 → 差距建议（mock 版：预置样例）"""
    matched = state.get("match_results") or []
    top = matched[0] if matched else ((state.get("target_jobs") or [{}])[0] or {})
    jd = top.get("jd") or top.get("snippet") or ""
    if RUN_MODE == "real" and jd:
        try:
            obj, _ = _llm_call(GAP_SYSTEM, _gap_prompt(jd, state.get("resume", {})))
            feedback = [f for f in (obj.get("feedback") or []) if isinstance(f, dict)
                        and (f.get("gap") or f.get("suggestion"))]
            if feedback:
                logger.info("N7 差距分析 真实 LLM: %d 条", len(feedback))
                return {"resume_feedback": feedback[: MAX_FEEDBACK_ITEMS]}
        except Exception as exc:  # noqa: BLE001
            logger.warning("N7 LLM 差距分析失败，降级预置: %s", exc)
    feedback = [
        {"gap": "JD 强调轨迹预测，简历缺少该关键词", "suggestion": "在项目描述中补充轨迹预测相关内容", "priority": "high"},
        {"gap": "项目量化不足", "suggestion": "补充指标（如精度提升百分比）", "priority": "mid"},
    ][: MAX_FEEDBACK_ITEMS]
    return {"resume_feedback": feedback}


# ---------- N8 简历改进 ----------
def resume_improve(state: JobHunterState) -> Dict[str, Any]:
    """带建议重新生成简历（复用 N3 逻辑；骨架版直接再生成一轮）"""
    new = resume_generate(state)
    new["match_round"] = state.get("match_round", 0) + 1
    return new


# ---------- N6 面试准备 ----------
def _materials_html(files: list) -> str:
    """面试材料列表 → 内联 HTML 预览（前端 mat-frame srcdoc 渲染契约）。"""
    import html as _html
    body = "".join(
        f"<section><h3>{_html.escape(str(f.get('name', '')))}</h3>"
        f"<pre>{_html.escape(str(f.get('content', '')))}</pre></section>"
        for f in files)
    return ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<style>body{font-family:sans-serif;max-width:760px;margin:24px auto;}"
            "section{margin-bottom:20px;border-bottom:1px solid #eee;}"
            "h3{margin-bottom:4px;}pre{white-space:pre-wrap;font-family:inherit;}</style>"
            f"</head><body>{body}</body></html>")


def _fallback_materials(resume: Dict[str, Any], jd: str, title: str) -> Dict[str, Any]:
    """组件降级：确定性骨架材料（结构对齐 prep_agent 契约，无外部服务依赖）。"""
    name = (resume.get("basicInfo") or {}).get("name") or "求职者"
    hint = "（降级模式：配置 LLM API Key 后重新生成完整材料）"
    files = [
        {"name": "01_自我介绍.md", "content": f"# 自我介绍\n\n你好，我是{name}，应聘{title}。\n\n{hint}"},
        {"name": "02_项目深挖.md", "content": f"# 项目深挖\n\n{hint}"},
        {"name": "05_面经.md", "content": f"# 面经与面试题库\n\n岗位 JD：{jd[:200]}\n\n{hint}"},
    ]
    return {"files": files, "quality_summary": [], "html": _materials_html(files),
            "raw": [{"name": f["name"], "content": f["content"]} for f in files]}


def prep_materials(state: JobHunterState) -> Dict[str, Any]:
    """进程内 prep_agent 链生成面试材料（含质量回路 D1~D5 结果）。
    组件异常 → 降级为预置骨架材料（确定性，无外部服务依赖）。"""
    resume = state.get("resume", {})
    matched = state.get("match_results") or []
    top = matched[0] if matched else ((state.get("target_jobs") or [{}])[0] or {})
    company = top.get("company") or ""
    title = top.get("title") or "目标岗位"
    jd = top.get("jd") or top.get("snippet") or ""
    inputs = {
        "resume": resume,
        "company": company,
        "job": {"name": title},
        "jd_text": jd,
        "resume_ver": (resume.get("line") or "line-mock"),
    }
    try:
        out = _run_prep_chain(inputs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("N6 prep_agent 组件异常，降级预置材料: %s", exc)
        return {"interview_materials": _fallback_materials(resume, jd, title),
                "errors": state.get("errors", []) + [f"prep_agent 组件降级：{exc}"]}
    materials = out.get("materials") or []
    quality_summary = out.get("quality_summary") or []
    logger.info("N6 面试材料完成: %d 份, 质量回炉 %d 项", len(materials), len(quality_summary))
    return {"interview_materials": {
        "files": [{"name": m.get("name", ""), "content": m.get("content", "")} for m in materials],
        "quality_summary": quality_summary,
        "html": _materials_html([{"name": m.get("name", ""), "content": m.get("content", "")} for m in materials]),
        "raw": materials,
    }}


# ---------- N9 投递确认（人工确认点，Q10 语义扩展） ----------
def confirm_resume(state: JobHunterState) -> Dict[str, Any]:
    """human-in-the-loop：interrupt 展示 简历+达标岗位+投递清单（Q10，只推荐不引导），等用户决定。
    - 用户确认（approve）→ 清单置 confirmed → prep；提修改意见（modify+feedback）→ 回 N8；拒绝（reject+reason）→ END。
    - skip_confirm=true 时自动确认（测试/批量场景）。
    - 投递由用户独立完成（系统外）；进度用户手动录入 tracker（大脑只读）。"""
    approvals = dict(state.get("user_approvals", {}))
    plan = state.get("submission_plan") or {}
    matched = [r for r in state.get("match_results", []) if r["score"] >= MATCH_PASS_THRESHOLD]
    skip = (state.get("config") or {}).get("skip_confirm")
    # 注：langgraph interrupt 节点函数会执行两次（首次构建 payload / resume 后重新执行并返回），
    # 因此「进入」日志每条场景出现 2 次属正常机制，非重复调用 bug；「用户决定」只在 resume 后打印 1 次。
    logger.info("N9 投递确认 进入: match_round=%s matched=%d plan_total=%d plan_status=%s skip_confirm=%s",
                state.get("match_round"), len(matched),
                (plan.get("summary") or {}).get("total", len(plan.get("items", []))),
                plan.get("status"), skip)
    if not plan:
        logger.warning("N9 投递确认: submission_plan 为空（前置 build_submission_plan 未产出清单，正常路径不会发生）")
    if skip:
        logger.info("N9 投递确认: skip_confirm=true 自动确认 → prep")
        out = {"resume_decision": {"action": "approve", "auto": True},
               "user_approvals": {**approvals, "resume_final": "auto-approved(mock)"}}
        if plan:
            out["submission_plan"] = {**plan, "status": "confirmed"}
        logger.info("N9 投递确认 完成: 自动 approve, plan status=confirmed")
        return out
    decision = interrupt({
        "type": "confirm_resume",
        "resume": state.get("resume", {}),
        "matched": matched,
        "submission_plan": plan,  # Q10 投递清单：结构化推荐，用户参考后自行独立投递
    }) or {}
    action = decision.get("action", "approve")
    if action not in ("approve", "modify", "reject"):
        # 未知 action（前端异常/乱码）：保守按 reject 处理，避免误确认投递清单
        logger.warning("N9 投递确认: 未知 action=%r，按 reject 处理（避免静默确认）", action)
        decision = {**decision, "action": "reject", "reason": f"未知操作 {action!r}"}
        action = "reject"
    logger.info("N9 投递确认 interrupt 已发出: 展示 matched=%d plan_total=%d",
                len(matched), (plan.get("summary") or {}).get("total", len(plan.get("items", []))))
    logger.info("N9 投递确认 用户决定: action=%s decision=%s", action, decision)
    if action == "modify":
        feedback = list(decision.get("feedback", []))
        logger.info("N9 投递确认: modify → 回 N8 简历改进, feedback=%d 条", len(feedback))
        return {
            "resume_decision": decision,
            "resume_feedback": state.get("resume_feedback", []) + feedback,
            "user_approvals": {**approvals, "resume_final": "pending-modify"},
        }
    if action == "reject":
        reason = decision.get("reason", "用户拒绝定稿")
        logger.info("N9 投递确认: reject → END, reason=%s", reason)
        return {
            "resume_decision": decision,
            "user_approvals": {**approvals, "resume_final": "rejected",
                               "reject_reason": reason},
        }
    logger.info("N9 投递确认: approve → prep, 投递清单置 confirmed")
    out = {"resume_decision": decision,
           "user_approvals": {**approvals, "resume_final": "approved"}}
    if plan:
        out["submission_plan"] = {**plan, "status": "confirmed"}
    return out


# ---------- N10 面试跟踪 ----------
def track_jobs(state: JobHunterState) -> Dict[str, Any]:
    """本地 tracker 组件（components/tracker_agent）：投递/面试记录写入本地 JSON。
    支持用户通过 user_input.tracking 提供记录（模拟用户填报）；否则按达标岗位自动生成。"""
    records = (state.get("user_input") or {}).get("tracking")
    if not records:
        records = [
            {"job": r.get("title", ""), "status": "to_apply", "plan": "本周投递"}
            for r in state.get("match_results", []) if r.get("score", 0) >= MATCH_PASS_THRESHOLD
        ]
    try:
        all_records = _run_tracker(records)
    except Exception as exc:  # noqa: BLE001
        logger.warning("N10 tracker 本地存储失败，降级内存记录: %s", exc)
        return {"errors": state.get("errors", []) + [f"tracker: {exc}"],
                "tracking_records": records}
    return {"tracking_records": all_records}


# ---------- N11 总报告 ----------
def final_report(state: JobHunterState) -> Dict[str, Any]:
    """LLM 汇总 + 模板组装 → Markdown + JSON（骨架版：直接拼装）"""
    results = state.get("match_results", [])
    rr = state.get("review_results", {})
    review_line = "；".join(f"{b}: {r.get('verdict')}" for b, r in rr.items()) if rr else "无"
    report = {
        "resume_round": state.get("resume_round", 0),
        "match_round": state.get("match_round", 0),
        "verdict": state.get("gate_verdict", ""),
        "review_results": rr,                       # 审核状态透传到报告
        "matched": [r for r in results if r.get("score", 0) >= MATCH_PASS_THRESHOLD],
        "materials": (state.get("interview_materials") or {}).get("files", []),
        "tracking": state.get("tracking_records", []),
        "errors": state.get("errors", []),
        "markdown": (
            f"# 求职报告\n"
            f"- 简历迭代: {state.get('resume_round', 0)} 轮\n"
            f"- 简历审核: {review_line}\n"
            f"- 匹配轮次: {state.get('match_round', 0)} 轮, 判定: {state.get('gate_verdict', '')}\n"
            f"- 达标岗位: {len([r for r in results if r.get('score', 0) >= MATCH_PASS_THRESHOLD])} 个\n"
            f"- 面试材料: {len((state.get('interview_materials') or {}).get('files', []))} 份\n"
        ),
    }
    return {"report": report}


# ---------- N12 降级标记 ----------
def degrade_mark(state: JobHunterState) -> Dict[str, Any]:
    """反馈环到上限：标记 accept_with_issues，继续流程"""
    return {
        "gate_verdict": "accept_with_issues",
        "errors": state.get("errors", []) + ["匹配未达标但已达轮次上限，降级继续"],
    }
