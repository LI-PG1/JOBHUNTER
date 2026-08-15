"""Prompt 组装（契约 §6.10 八层结构）。

第 1 层 系统人设 / 第 2 层 简历数据 / 第 3 层 JD / 第 4 层 共享事实表 /
第 5 层 规则与风格 / 第 6 层 输出格式（含自估协议）/ 第 7 层 预算约束 / 第 8 层 合规边界。

P3 落地：JD 分析、技能相关性评分。P4 扩展各生成板块。
"""
import json
from typing import List

SYSTEM_PERSONA = (
    "你是一名资深 HR 与求职导师，精通中文简历撰写与 ATS（申请追踪系统）解析规则。"
    "你坚持「真实优先」：绝不虚构经历、公司、职级、奖项与业务数据；"
    "需要数值时给出合理、符合行业常规精度（如百分比 1 位小数、延迟 100~200ms、QPS 数百）的数字，"
    "并始终以「可被面试追问验证」为标准措辞。"
)


def jd_analysis_messages(jobs: List[dict], rules: dict, factsheet_input: dict) -> List[dict]:
    """JD 分析 → 共享事实表（§5.2）。factsheet_input 提供 identity/pageOption/density 上下文。"""
    system = SYSTEM_PERSONA + (
        "\n\n你是 JD 分析器：从 1~5 套岗位 JD 中提炼职业方向与简历生成所需的关键事实，"
        "输出严格 JSON，不要输出任何解释或 markdown。"
    )
    user = f"""请分析以下目标岗位 JD（{len(jobs)} 套，属同一职业方向），输出共享事实表 JSON：

【JSON 输出结构】
{{
  "direction": "职业方向（如 AI Agent / LLM 应用）",
  "coreSkills": ["岗位最看重的 3~5 个技能/领域，用于定向优化简历"],
  "jdFocus": "JD 的核心诉求（1 句话）",
  "projectType": "最匹配的项目类型（参考可用类型）",
  "metricStyle": "该岗位成果量化的风格约定（参考给定风格，可改写为贴合 JD）",
  "domainTags": ["领域标签 2~4 个，用于主题一致性校验"],
  "keywordCoverage": 0.0
}}

【岗位 JD】
{"\n---\n".join(f"岗位：{j['title']}\nJD：{j['jdText']}" for j in jobs)}

【行业规则参考】
可用项目类型：{rules.get('project_types', [])}
量化风格参考：{rules.get('metric_style', '')}
主题一致性方法：{rules.get('jobs', {}).get('method', 'shared-domain-tag')}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def skill_validate_messages(skills: List[dict], jobs: List[dict], rules: dict) -> List[dict]:
    """技能相关性评分（§3.1.4 / §4.2 /api/skills/validate）。"""
    system = SYSTEM_PERSONA + (
        "\n\n你是技能匹配评估器：评估「用户技能列表」与「目标岗位 JD」的相关度，"
        "输出严格 JSON：{\"score\": 0~1, \"reason\": \"中文理由\"}。"
        "分数含义：≥0.6 强相关；0.3~0.6 部分相关；<0.3 明显不相关。"
    )
    user = f"""【用户技能】{", ".join(f"{s.get('name','')}" for s in skills)}

【目标岗位 JD】
{"\n---\n".join(f"岗位：{j.get('title','')}\nJD：{j.get('jdText','')}" for j in jobs)}

【评分要求】结合 JD 核心关键词评估相关度，仅输出 JSON。"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def theme_check_messages(jd_tags: List[str], resume_tags: List[str], threshold: float) -> List[dict]:
    """主题一致性语义兜底（§3.1.6）：领域标签共享 <1 时评估语义相关度。"""
    system = SYSTEM_PERSONA + (
        "\n\n你是主题一致性评估器：判断「目标岗位领域标签」与「求职者经历领域标签」是否属于同一方向，"
        "输出严格 JSON：{\"score\": 0~1, \"reason\": \"中文理由\"}。"
        f"score ≥{threshold} 视为同一方向。"
    )
    user = f"""【岗位领域标签】{", ".join(jd_tags) if jd_tags else "（无）"}
【简历领域标签】{", ".join(resume_tags) if resume_tags else "（无）"}

仅输出 JSON。"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def skill_extend_messages(skills: List[dict], jobs: List[dict]) -> List[dict]:
    """技能拓展（§4.2 /api/skills/extend）：基于 JD 推荐补充技能（有机分类）。"""
    system = SYSTEM_PERSONA + (
        "\n\n你是技能规划导师：基于目标岗位 JD 与用户现有技能，推荐 3~6 个补充技能，"
        "并给出**有机分类**（如 专业技能 / 工具与框架 / 语言能力 / 深度学习框架 / 推理部署 / 模型优化 / 应用开发，"
        "可自定义更贴切类别，用于简历技能板块按类别分行展示）。"
        "分类硬约束：总分类数 3~5 个；优先复用用户已有分类；每个分类至少 2 个技能"
        "（「语言能力」可单条，但名称必须带等级/分数标注，如 英语（CET-6 通过）、雅思（7.0）、日语（N2））；"
        "**严禁出现仅含 1 个技能的碎分类**——单独的技能并入相近大类，不单独占一行。"
        "输出严格 JSON：{\"recommended\": [{\"category\": \"类别\", \"name\": \"技能名\", \"level\": \"精通|熟练|熟悉|了解\"}]}。"
        "仅推荐与 JD 强相关、用户真实可具备（学习/练习可掌握）的技能，不虚构资质。"
    )
    user = f"""【用户现有技能】{", ".join(f"{s.get('name','')}" for s in skills)}

【目标岗位 JD】
{"\n---\n".join(f"岗位：{j.get('title','')}\nJD：{j.get('jdText','')}" for j in jobs)}

仅输出 JSON。"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ---------------------------------------------------------------- P4 分块生成（§5.1/§5.3）


def _estimated_protocol() -> str:
    """自估协议（§5.3）：每个文本条目输出预估渲染行数。"""
    return (
        "【自估协议】每条正文（text/sentences/duties/items）必须附带 estimatedLines（整数 1~8），"
        "表示该条在 A4 单栏、正文 10.5pt、默认行距下预估渲染的行数，供排版预算校准。"
    )


def summary_messages(user_brief: dict, rules: dict, factsheet: dict) -> List[dict]:
    """自我评价生成（第一层）：最多 2 句，简洁不重复基本信息，有机呼应目标岗位能力需要。"""
    core = factsheet.get("coreSkills") or []
    focus = factsheet.get("jdFocus") or ""
    jd_ref = ""
    if core or focus:
        jd_ref = (
            "【目标岗位能力需要（来自 JD 分析）】\n"
            f"岗位核心技能：{', '.join(core)}\n岗位核心诉求：{focus}\n"
            "自我评价应自然呼应其中 2~3 项能力，避免逐条罗列。"
        )
    system = SYSTEM_PERSONA + (
        "\n\n你是简历自我评价撰写师：写 1~2 句简洁有力的自我评价，一句话讲清一个点（自然成句即可，无需逐字计数）。"
        "第一句定位：突出与目标岗位匹配的核心能力与真实经验；第二句（可选）体现工作方式/学习能力/责任心。"
        "要求：不重复姓名、年龄、联系方式、学校名称等基本信息；不虚构奖项与经历；"
        "有机呼应目标岗位的能力需要，而非泛泛而谈。输出严格 JSON。"
    )
    user = f"""{_estimated_protocol()}

【用户概要】
{json.dumps(user_brief, ensure_ascii=False, indent=2)}

{jd_ref}

【风格参考】{rules.get('tone', '')}

【JSON 输出结构】
{{"sentences": [{{"text": "自我评价句子（40~80 字）", "estimatedLines": 1}}]}}

仅输出 JSON。"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def internship_messages(internships: List[dict], rules: dict) -> List[dict]:
    """实习美化（第一层，有则做）：仅优化措辞、补合理量化，不创造经历。

    输出对齐高密度简历范式：overview=主要职责概述（1 句）；duties=主要工作内容
    2~4 条主题化条目，每条「主题：内容描述（技术栈 + 量化成果）」。
    """
    system = SYSTEM_PERSONA + (
        "\n\n你是实习经历润色师：在**不改变公司/职位/时间/职责事实**的前提下，把实习经历润色为高信息密度结构。"
        "**以用户填写的实习经历（公司/职位/时间/职责方向）为唯一事实依据**：仅围绕用户给出的职责内容做润色与合理量化补充，"
        "不得把用户实习改写成其他公司的经历，不得虚构用户未提供的职责方向。"
        "输出结构：overview=主要职责概述（一句话讲清平台/职责范围与核心产出方向）；"
        "duties=主要工作内容 2~4 条，每条格式为「主题：内容描述（含技术方案与量化成果）」，例如："
        "「大模型全链路部署交付：独立完成 30+ 大模型从选型到公网推理服务的端到端交付，覆盖文本生成、多模态、OCR 等品类，"
        "技术栈 Python/PyTorch/vLLM，Docker 容器化 + FastAPI/Gradio 服务化」。"
        "要求：动词开头、写清具体负责的技术/业务动作、关键实现方式或技术方案，"
        "**每条必须含量化成果或明确指标**（QPS、时延、准确率/召回率、数量规模、成本收益等具体数字；"
        "确实无法量化的写明覆盖范围/规模/频次），按重要性排序，保留 2~4 条最有价值的主题。输出严格 JSON。"
    )
    user = f"""{_estimated_protocol()}

【用户实习】
{json.dumps(internships, ensure_ascii=False, indent=2)}

【量化风格】{rules.get('metric_style', '')}

【写作风格参考（模仿其信息密度与结构，不得照抄内容/数据）】
实习：大模型应用开发工程师（AI-Agent 方向）
- 主要职责：基于 GPU 云平台制作镜像并部署大模型上线，为客户的大模型业务需求（RAG、Agent、量化、调优等）设计技术方案并搭建框架化运行环境。
- 大模型全链路部署交付：独立完成 30+ 大模型从选型到公网推理服务的端到端交付，覆盖文本生成、多模态、视觉定位与 VLM、MoE、OCR、图像/视频生成等品类，技术栈 Python/PyTorch/vLLM，Docker 容器化 + FastAPI/Gradio 服务化。
- RAG 与 Agent 服务框架搭建：部署 Embedding 向量化与 Rerank 精排微服务，对接向量数据库搭建语义检索链路；部署对话模型推理服务与工具调度链路，形成按需组合的 RAG/Agent 基础服务矩阵。
- 大模型参数微调：PEFT/LoRA/QLoRA + Transformers Trainer + DeepSpeed ZeRO，完成模型训练、权重合并与多维度效果评估。

【JSON 输出结构】
{{"items": [{{"company": "公司", "position": "职位", "startMonth": "2024.06", "endMonth": "2024.09",
  "overview": "主要职责概述（1 句）",
  "duties": [{{"text": "主题：内容描述（技术栈 + 量化成果）", "estimatedLines": 1}}]}}]}}

仅输出 JSON；保留全部公司/职位/时间原值。"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def projects_messages(
    seeds: List[dict],
    skeleton: str,
    factsheet: dict,
    rules: dict,
    count: int,
    limit: int,
    search_results: List[dict],
) -> List[dict]:
    """项目生成（第二层，依赖共享事实表）：已有项目润色补齐，空位按骨架创造。

    items 覆盖 STAR 段：limit=6（两页 2 项目）为背景/任务/行动×3/结果；
    limit=4（STAR 四段：背景/任务/行动×1~2/结果）；limit=3（一页多项目：背景与任务/行动/结果）。
    """
    seg = {
        6: "两页版恰好 6 条（背景 1 + 任务 1 + 行动 3 + 结果 1）",
        4: "恰好 4 条（背景 1 + 任务 1 + 行动 1~2 + 结果 1）",
        3: "恰好 3 条（背景与任务 1 + 行动与方案 1 + 结果与复盘 1）",
    }.get(limit, f"恰好 {limit} 条")
    system = SYSTEM_PERSONA + (
        "\n\n你是项目经历撰写师：面向目标岗位定向产出 {count} 条 STAR 结构项目。"
        "**用户已有项目（source=polished）：名称/角色/时间/技术栈/项目方向一律保留，仅做 STAR 四段结构化扩充**"
        "（补背景与量化基线、任务与量化目标、行动技术细节、结果与复盘），"
        "不得把用户项目改写成其他方向，不得编造用户未提供的项目类型；"
        "空位 → 基于给定骨架创作可验证的课程/竞赛/自研项目（source=ai-created），不虚构公司职级。"
        "每个项目的要点（items）必须完整覆盖 STAR 结构："
        "①背景与问题（S）：业务/场景痛点 + 量化基线；②任务与目标（T）：你负责的范围 + 明确的量化目标；"
        "③行动与方案（A）：写清技术框架/库/关键参数、工程决策与实现方式；"
        "④结果与复盘（R）：量化成果 + 一句复盘洞察（为什么有效/可复用的经验）。"
        "要点数量为硬约束：{seg}，不得少于该数量。"
        "每条要点是一句完整叙事（信息密度高，无需逐字计数），含量化指标与工程细节，避免空泛形容词。"
        "每条 2~3 行。输出严格 JSON。"
    ).format(count=count, seg=seg)
    user = f"""{_estimated_protocol()}

【共享事实表】{json.dumps(factsheet, ensure_ascii=False, indent=2)}

【用户已有项目（可作种子）】
{json.dumps(seeds, ensure_ascii=False, indent=2) if seeds else "（无）"}

【空位骨架】{skeleton or "（无，按事实表 projectType 创作）"}

【量化风格】{rules.get('metric_style', '')}

【写作风格参考（模仿其信息密度与结构，不得照抄内容/数据；用户已有项目保持自身方向）】
项目 1：基于 LoRA 微调的领域问答助手
- 背景与问题：通用大模型在垂直领域知识覆盖不足，直接问答准确率仅 71%，且全参微调成本高昂、资源门槛高。
- 任务与目标：基于 Llama-3-8B 采用 LoRA 高效微调，构造 3 万条领域指令数据，将问答准确率提升至 89%，并验证 QLoRA 在显存占用上的收益。
- 行动与方案：使用 PyTorch/Transformers/PEFT 搭建 LoRA 微调流程，设计低秩适配层参数（秩、缩放因子、目标模块），冻结基座仅训练适配器；构造并清洗 3 万条指令数据，设计数据增强与去重策略；设计对比实验，同一基座与数据下对比 LoRA（16-bit）、QLoRA（4-bit）与全参微调的耗时、显存与效果。
- 结果与复盘：领域问答准确率 71%→89%；QLoRA 相对全参微调显存占用降低约 60%；复盘：LoRA 效果可逼近全参微调，QLoRA 进一步降低硬件门槛，是资源受限场景性价比最高的方案。

项目 2：多模态机器人推理服务部署（VLA）
- 背景与问题：VLA 模型在机器人场景需要实时响应，图像预处理与批处理策略不当导致时延波动大，无法满足实时控制要求。
- 任务与目标：使用 vLLM + Docker + FastAPI 搭建 VLA 推理服务，优化图像预处理与动态批处理策略，目标端到端时延稳定在 300ms 内、并发压测 P95 < 450ms。
- 行动与方案：vLLM 加载模型并配置 PagedAttention 与 Continuous Batching；将图像缩放/归一化/Token 化移到 GPU 或异步执行，减少 CPU-GPU 数据拷贝；根据请求到达率与 GPU 空闲动态调整 batch size 与调度窗口；FastAPI 封装 HTTP 服务内置超时与重试，Docker 打包镜像保证环境一致。
- 结果与复盘：端到端推理时延稳定在 300ms 内、并发压测 P95 < 450ms；复盘：动态批处理是时延优化的关键杠杆，图像预处理切分能显著减少单请求阻塞。

项目 3：面经知识库 RAG 检索系统
- 背景与问题：面试准备材料零散分布在大量面经中，简历与岗位 JD 匹配需快速检索归纳，手工整理效率低。
- 任务与目标：基于 LangChain + Chroma 构建面经知识库，实现简历-岗位匹配问答与面试题检索，目标 Top-5 检索命中率 ≥ 92%，并用 Gradio 搭建交互演示。
- 行动与方案：实现 RAG 全链路（文档加载→切分→Embedding→Chroma→检索 Top-K→Prompt 生成）；针对简历-岗位匹配设计查询改写策略（提取 JD 关键技能后与简历片段语义匹配）；Gradio 交互界面支持上传 JD 一键生成面试准备材料；对 chunk 大小、embedding 模型与 Top-K 做评测调优。
- 结果与复盘：Top-5 检索命中率达到 92%；复盘：RAG 上限取决于切分策略与查询改写质量，查询与文档的语义对齐比换 embedding 模型更关键。

【联网参考（标注待核实，不得照抄）】
{json.dumps(search_results, ensure_ascii=False, indent=2) if search_results else "（无）"}

【评估标准】{json.dumps(rules.get('evaluation', []), ensure_ascii=False, indent=2)}

【JSON 输出结构】
{{"projects": [{{"name": "项目名", "role": "角色", "startMonth": "2024.07", "endMonth": "2024.09",
  "techStack": ["技术1", "技术2"], "source": "polished|ai-created",
  "items": [{{"text": "STAR 四段要点（含量化指标）", "estimatedLines": 1}}]}}]}}

仅输出 JSON。"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
