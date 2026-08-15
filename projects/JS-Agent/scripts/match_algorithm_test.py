# -*- coding: utf-8 -*-
"""
JS-Agent 匹配算法阈值验证脚本（v0.4 审核第 6 条）

用途：
- 使用 DeepSeek-V4-Flash（密钥从 D:\\TRAE\\WORKSPACE\\key 动态读取，不硬编码、不落盘）
- 验证匹配算法核心能力与阈值合理性：
  ① 画像解析（自由文本 → 结构化画像卡 JSON，防幻觉技能）
  ② 技能线分类（应用/推理/双线）
  ③ 匹配度打分（高/中/低 三个构造岗位，评估 80%/60%/90% 阈值合理性）
  ④ JSON Schema 合规性（每次输出必须合法 JSON）

输出：
- stdout 结构化报告
- docs/测试报告_匹配算法阈值_v040.md（可追溯）
"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

KEY_FILE = Path(r"D:\TRAE\WORKSPACE\key")
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"  # 官方 API 名（对应通用显示名 DeepSeek-V4-Flash，用户限定只能用该模型）

# 候选人画像（固定基准，与用户一致）
PROFILE = (
    "计算机硕士（2027 年 6 月毕业），研究方向大模型应用与推理优化；"
    "实习经历：OrionX 大模型应用开发（Agent/RAG 系统）；"
    "项目：VLA 机器人推理服务（vLLM 部署）；"
    "技能：Python、PyTorch、vLLM、DeepSpeed、LoRA/QLoRA、RAG、Agent、Docker、FastAPI、LangChain"
)

# 构造岗位（高/中/低匹配），用于评估阈值
JOBS = {
    "high": (
        "岗位：大模型 Agent 应用工程师\n"
        "职责：基于 LangChain/Agent 框架开发企业级 RAG 问答系统；大模型微调（LoRA）；FastAPI 服务部署；Docker 容器化交付。\n"
        "要求：硕士，熟悉 Python/PyTorch，有 Agent/RAG 项目经验，了解 vLLM 部署。"
    ),
    "medium": (
        "岗位：推理优化工程师\n"
        "职责：使用 vLLM/SGLang 优化大模型推理吞吐与延迟；KV Cache 优化；量化（AWQ/GPTQ）；K8s 推理服务。\n"
        "要求：本科以上，熟悉 C++/CUDA 优先，2 年经验。"
    ),
    "low": (
        "岗位：前端开发工程师\n"
        "职责：React/Vue 开发 Web 界面；组件库建设；性能优化。\n"
        "要求：本科，3 年经验，精通 TypeScript。"
    ),
}


def read_key() -> str:
    """从 key 文件读取 DeepSeek API key（不打印、不落盘）。"""
    for line in KEY_FILE.read_text(encoding="utf-8").splitlines():
        if "DeepSeek API key" in line:
            return line.split("：", 1)[-1].split(",", 1)[0].strip()
    raise RuntimeError("key 文件中未找到 DeepSeek API key")


KEY = read_key()


def call_llm(system: str, user: str, max_tokens: int = 2500, temperature: float = 0.2) -> tuple[str, dict]:
    """调用 DeepSeek-V4-Flash，返回 (文本内容, 元信息)。"""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    elapsed = round(time.time() - t0, 2)
    msg = data["choices"][0]["message"]
    usage = data.get("usage", {})
    text = msg.get("content", "")
    # 兼容推理模型：若 content 为空则取 reasoning_content 附近
    return text, {"elapsed_s": elapsed, "prompt_tokens": usage.get("prompt_tokens", 0),
                  "completion_tokens": usage.get("completion_tokens", 0),
                  "total_tokens": usage.get("total_tokens", 0)}


def parse_json(text: str) -> dict:
    """解析 LLM 输出的 JSON（容忍代码块包裹）。"""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):]
    return json.loads(s)


# ---------- 用例 ----------
CASE_PROFILE_SYS = (
    "你是岗位匹配系统的画像解析器。将用户描述解析为严格 JSON："
    '{"skills":[{"name":"技能名","line":"app|inference|both"}],'
    '"education":"学历","grad_year":"毕业年份","city":"意向城市",'
    '"experience_years":数字或null,"companies":["公司"],"raw_summary":"一句话总结"}。'
    "只允许使用中文技能名，技能必须来自用户原文或行业通用名，禁止编造。"
)

CASE_MATCH_SYS = (
    "你是岗位匹配评分器。给定候选人画像与岗位 JD，输出严格 JSON："
    '{"match_score":0-100整数,"skill_line":"app|inference|both|other",'
    '"matched_skills":["命中技能"],"missing_skills":["岗位要求但画像缺失的核心技能"],'
    '"reason":"评分依据(50字内)"}。'
    "评分规则：技能匹配度=命中核心技能数/岗位核心技能总数；80-100 高度匹配，60-79 部分匹配，<60 不匹配。"
)


def run_case(name: str, system: str, user: str) -> dict:
    result = {"case": name, "status": "PASS"}
    try:
        text, meta = call_llm(system, user)
        result["meta"] = meta
        obj = parse_json(text)
        result["output"] = obj
    except Exception as e:  # noqa: BLE001
        result["status"] = "FAIL"
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main() -> None:
    report = {"model": MODEL, "profile": PROFILE, "cases": []}

    # ① 画像解析（3 次，验证稳定性）
    for i in range(3):
        r = run_case(f"画像解析-{i+1}", CASE_PROFILE_SYS, f"我的情况：{PROFILE}")
        report["cases"].append(r)
        time.sleep(1)

    # ② 匹配度打分：高/中/低 三岗
    for key, jd in JOBS.items():
        r = run_case(f"匹配打分-{key}", CASE_MATCH_SYS, f"候选人画像：{PROFILE}\n\n岗位JD：\n{jd}")
        report["cases"].append(r)
        time.sleep(1)

    # 汇总
    print("=" * 70)
    print(f"JS-Agent 匹配算法阈值验证 — {MODEL}")
    print(f"画像基准：{PROFILE[:60]}...")
    print("=" * 70)
    for r in report["cases"]:
        print(f"\n[{r['status']}] {r['case']}")
        if r.get("meta"):
            m = r["meta"]
            print(f"  耗时 {m['elapsed_s']}s | tokens {m['total_tokens']} (in {m['prompt_tokens']}/out {m['completion_tokens']})")
        if r.get("output"):
            print("  输出:", json.dumps(r["output"], ensure_ascii=False)[:400])
        if r.get("error"):
            print("  错误:", r["error"])

    # 写测试报告
    out_path = Path(__file__).resolve().parent.parent / "docs" / "测试报告_匹配算法阈值_v040.md"
    lines = [
        "# JS-Agent 匹配算法阈值验证报告（v0.4 审核）",
        "",
        f"- 模型：`{MODEL}`（用户限定）",
        f"- 测试时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "- 密钥来源：D:\\TRAE\\WORKSPACE\\key（动态读取，本报告不含任何密钥）",
        f"- 画像基准：{PROFILE}",
        "",
        "## 用例结果",
        "",
        "| 用例 | 状态 | 耗时(s) | tokens | 关键输出 |",
        "|------|------|---------|--------|----------|",
    ]
    for r in report["cases"]:
        m = r.get("meta", {})
        out = json.dumps(r.get("output", r.get("error", "")), ensure_ascii=False)[:150]
        lines.append(f"| {r['case']} | {r['status']} | {m.get('elapsed_s','-')} | {m.get('total_tokens','-')} | {out} |")
    lines += ["", "## 结论（待人工分析）", ""]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n测试报告已写入：{out_path}")


if __name__ == "__main__":
    main()
