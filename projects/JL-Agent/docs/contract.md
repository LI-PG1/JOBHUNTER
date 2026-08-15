# 简历生成助手工程契约（P0 定稿）

> 版本：v1.0（P0 产出，2026-08-07）
> 上游依据：PRD v0.6、模板 resume-1page/2pages.html、实施计划 P0 阶段
> 门禁：**M0 —— 本文档经用户评审批准后，方可进入 P1 骨架开发**
> 用途：前后端共同契约。前端实现依据 §3/§4（字段与接口）；后端实现依据 §3~§6；验收依据 §7。

---

## 1. 技术栈与运行环境

| 项 | 定稿 |
|---|---|
| 语言/框架 | Python 3.10+ / FastAPI / uvicorn；前端原生 HTML/CSS/JS（零构建） |
| 依赖 | fastapi、uvicorn、pydantic v2、httpx、python-dotenv、Pillow、jsonschema；PDF 方案选型后再加（§3.1.9） |
| 运行形态 | **本地单用户**（§7）：`uvicorn app.main:app` 本地启动；无云服务、无独立 DB、无鉴权；生成任务**单任务串行** |
| 存储 | 本地 JSON 文件：`data/resumes/{id}.json`、`data/tasks/{id}.json`（运行态）、`data/photos/{id}.{ext}`、`data/calibration.json`（预算校准） |
| 密钥 | `.env`（真实密钥，不入库）；`config.example.json` 随仓库发布；API Key 脱敏展示（maskKey） |
| LLM | provider 适配层，默认 DeepSeek（openai 兼容接口）；`config.json` 可配 base_url/api_key/model；**UI 不展示模型名** |

设计约束：不引入任务队列（串行即可）；不引入数据库服务；规则文件用 jsonschema 校验后加载；所有 LLM 调用走统一 provider 接口（便于后续加多 provider 冗余）。

---

## 2. 目录结构

```
JL-Agent/
├── README.md
├── config.example.json        # 配置样例（随仓库发布）
├── .env.example               # 密钥样例
├── .gitignore                 # 忽略 .env / data/ 等
├── requirements.txt
├── app/
│   ├── main.py                # FastAPI 入口，挂载路由与静态文件
│   ├── config.py              # 配置加载：.env + config.json 合并、maskKey
│   ├── storage.py             # 本地 JSON 持久化（resumes/tasks/photos）
│   ├── schemas/               # Pydantic 模型（= 数据契约 §3）
│   │   ├── resume.py          # Resume/BasicInfo/Photo/Education/Internship/Project/Summary/Skill/Honor
│   │   ├── jobs.py            # Job/Direction/JDAnalysis（共享事实表）
│   │   ├── task.py            # Task/Progress/SSE 事件模型
│   │   └── common.py          # 枚举、错误码 envelope
│   ├── api/                   # 路由层（薄，只做参数校验与调用）
│   │   ├── resume.py          # CRUD
│   │   ├── upload.py          # 照片上传
│   │   ├── generate.py        # 创建任务 + 状态 + SSE + 取消
│   │   ├── projects.py        # 项目生成/重生成/美化/库
│   │   ├── skills.py          # 相关性校验 / 拓展
│   │   ├── search.py          # 搜索模式 / 深度取材
│   │   ├── adjust.py          # 适配调整（前端测量 → 后端配置+重写）
│   │   ├── export.py          # HTML / PDF（PDF 后置）
│   │   └── init.py            # 初始化引导 / 能力检测 / 配置
│   ├── core/
│   │   ├── validation.py      # 数据校验（时间/枚举/邮箱/电话/上限）
│   │   ├── rules.py           # 规则文件 loader + jsonschema 校验 + 版本号
│   │   ├── providers.py       # LLM provider 适配层（chat/json_mode/自估元数据）
│   │   └── errors.py          # 错误码定义（§4.1）
│   ├── engine/
│   │   ├── analysis.py        # JD 分析 + 主题一致性 + 领域标签
│   │   ├── factsheet.py       # 共享事实表构建（§5.2）
│   │   ├── dag.py             # 分层并行调度 + 板块级进度上报（§5.1）
│   │   ├── prompts.py         # 8 层 Prompt 组装（含自估输出协议）
│   │   ├── blocks/            # 分块生成器：summary / education / internship / projects / skills / honor
│   │   ├── review.py          # criticality 标注 + 批判性审阅（建议层）
│   │   ├── budget.py          # 高精度预算：自估 + 校准表 + 修正（§5.3）
│   │   └── cache.py           # 增量缓存 key + 失效规则（§5.4）
│   ├── adapter/
│   │   ├── plan.py            # 适配决策：超/不足 → 配置+重写指令（§6）
│   │   └── apply.py           # 排版层配置（body[data-density]）与内容层配置序列化
│   ├── search/
│   │   ├── api_search.py      # Tavily/Serper（限频 1.1s 间隔，降级）
│   │   └── deep_mode.py       # BrowserSkill（默认关、固定限频、HITL、缺失降级）
│   └── assets/                # 模板注入辅助（占位符替换、空区块删除、照片位）
├── rules/                     # 规则文件（独立于代码，版本化）
│   ├── schema/                # 各规则文件 jsonschema
│   ├── industries/            # 行业模板库（先 5 个：互联网/金融/快消/制造/游戏）
│   ├── projects/              # JD 方向 ↔ 项目类型映射 + 评估标准
│   ├── skills/                # 技能相关性判定规则
│   └── jobs/                  # 主题一致性判定规则
├── templates/
│   ├── resume-1page.html
│   └── resume-2pages.html
├── frontend/
│   ├── index.html             # 单页应用壳
│   ├── css/app.css            # 基础样式（复用 MS-Agent 风格 token）
│   └── js/
│       ├── app.js             # 路由/状态/toast
│       ├── form.js            # 表单分区 + 动态增删（教育 3/实习 2/JD 5）
│       ├── photo.js           # 照片上传校验与预览
│       ├── validate.js        # 前端预校验 + 提交关卡调用
│       ├── generate.js        # SSE 进度条 + 预览
│       ├── edit.js            # 预览编辑、编辑锁定、单条重生成
│       ├── adapt.js           # 适配闭环：测量 → /api/adjust → 应用（≤3 轮）
│       └── export.js          # 导出确认清单 + 练习/正式版 + 打印/PDF
└── data/                      # 运行时数据（gitignore）
```

---

## 3. 数据契约（字段级）

统一规范：时间一律 `YYYY.MM` 字符串；金额/比例等数字用 number；所有枚举见 §3.4。

### 3.1 Resume 顶层

```json
{
  "id": "res_20260807_xxxx",
  "version": "intern-version | fall-version",
  "identity": "intern | fulltime",
  "createdAt": "2026-08-07T10:00:00+08:00",
  "updatedAt": "...",
  "basicInfo": {},
  "photo": {},
  "education": [],
  "internship": [],
  "project": [],
  "summary": [],
  "skill": [],
  "honor": [],
  "jobs": [],
  "direction": "",
  "pageOption": "one-page | two-pages",
  "density": "compact | normal | loose",
  "contentPlan": {},
  "generation": {}
}
```

### 3.2 实体字段

| 实体 | 字段（类型 / 必填 / 校验） | 说明 |
|---|---|---|
| BasicInfo | 姓名 str 必填；年龄 int 必填 16~70；邮箱 email 必填；电话 str 必填（11 位手机或含区号）；个人网页 url 选填；base str 选填；可实习时长 str 选填（秋招版=入职时间）；到岗时间 str 选填 | 简历不展示目标岗位 |
| Photo | dataUrl str 选填；filePath str；width/height int；ratio str "3:4"\|"4:5"；format "jpg"\|"png" | 校验见 §4.2 upload |
| Education | 学校 str 必填；专业 str 必填；学位 enum 必填；startMonth/endMonth `YYYY.MM` 必填，end>start；≤3 条 | 时间倒序 |
| Internship | 公司 str 必填；职位 str 必填；startMonth/endMonth；duties[] 每条 `{text, criticality}`；≤2 段；空数组 → 整块隐藏 | 仅美化不创造 |
| Project | 名称 str 必填；角色 str；startMonth/endMonth；techStack[]；items[]（STAR 自然段落，每条 `{text, criticality}`）；source enum；aiFlag bool；≤ 硬性约束条数 | 条数由 §6.4 定死 |
| Summary | sentences[] 每条 `{text, criticality}`；1~3 句；用户可增删 | 弹性板块 |
| Skill | 分类 enum（专业技能/工具与框架/语言能力）；名称 str 必填；level enum 选填（精通/熟练/熟悉/了解）；skillExtend bool | 至少 1 条 |
| Honor | 名称 str 必填；机构 str；时间 str；criticality 默认 low；空 → 整块隐藏 | 非常驻 |
| Job | 岗位 str 必填；jd 文本 str 必填；1~5 套；领域标签（分析后写入） | 同一职业方向 |
| Direction | str，分析结果，仅生成上下文，不在简历展示 | |
| ContentPlan | `{detailLevel: "详细|标准|精简", projectCount, bulletCountPerProject, summarySentenceCount}` | 描述性板块 |
| Generation | `{taskId, stages: [...], watermarkMode, deepSearch, source 记录, 校准数据引用}` | 追溯 |

### 3.3 校验规则（数据层，集中实现）

| 规则 | 实现点 |
|---|---|
| 时间格式 `YYYY.MM` 正则 `^\d{4}\.(0[1-9]|1[0-2])$` | validation.py |
| 结束 > 开始（教育/实习/项目） | validation.py |
| 学位枚举：学士/硕士/博士/专科 | validation.py |
| 邮箱/电话格式 | validation.py |
| 数量上限：教育 ≤3、实习 ≤2、JD ≤5、项目条数按 §6.4 映射表硬性 | validation.py + §6.4 |
| 技能必填 ≥1 条；相关性校验（§3.1.4：≥0.6 通过 / 0.3~0.6 弱提示 / <0.3 阻止 + 关键词兜底） | /api/skills/validate |
| 主题一致性（§3.1.6：领域标签共享 ≥1 或语义 ≥0.4） | engine/analysis.py |
| 照片（§3.1.7：JPG/PNG、200~4000px、≤5MB、比例提示不拦截） | /api/upload/photo |

### 3.4 枚举定稿

- `identity`: intern（实习生）| fulltime（全职）
- `version`: intern-version | fall-version
- `pageOption`: one-page | two-pages
- `density`: compact | normal | loose
- `detailLevel`: 详细 | 标准 | 精简
- `criticality`: critical | high | medium | low（**critical 绝不裁剪**；用户手动编辑项自动 critical）
- `source`: user-input | polished | ai-created（合规标记，驱动来源徽标/确认清单）
- `学位`: 学士 | 硕士 | 博士 | 专科
- `skillExtend`: false | true

### 3.5 数量硬性约束（§6.4 落地为代码常量表，禁止漂移）

| 实习条数 | 一页项目条数 | 两页项目条数 |
|---|---|---|
| 0 | 2 | 3 |
| 1 | 1 | 2 |
| 2 | 1 | 1 |

压缩/扩充**不增减项目条数**，只调每条要点数与详略。

---

## 4. API 契约

### 4.1 通用约定

- Base URL：`http://127.0.0.1:8000`；JSON 请求/响应；文件上传 multipart。
- 响应 envelope：
  - 成功：`{"code": 0, "message": "ok", "data": {...}}`
  - 失败：`{"code": 40001, "message": "中文可读提示", "detail": {...}}`
- 错误码：
  - `40001` 参数校验失败；`40002` 技能相关性不通过；`40003` 主题一致性不通过；`40004` 照片格式不支持；`40005` 照片尺寸超限；`40006` 照片大小超限；`40007` 教育时间非法；`40008` 任务不存在；`40009` 任务状态冲突；`40010` 导出确认清单未完成；`40011` 数量上限（教育3/实习2/JD5）；`40012` 编辑锁定项不可自动重写
  - `50001` 规则文件缺失/校验失败；`50002` LLM 调用失败；`50003` 搜索失败（可降级，不阻塞）；`50004` 板块生成失败（模块级降级）

### 4.2 接口清单

| 方法 | 路径 | 请求 | 响应 data | 主要错误 |
|---|---|---|---|---|
| POST | /api/resume | Resume JSON（无 id 则新建） | `{resumeId}` | 40001/40007/40011 |
| GET | /api/resume/{id} | — | Resume JSON | 40008 |
| PUT | /api/resume/{id} | Resume JSON（整存） | `{updatedAt}` | 40001/40008 |
| DELETE | /api/resume/{id} | — | `{deleted:true}` | 40008 |
| POST | /api/upload/photo | multipart(file, resumeId) | `{dataUrl,width,height,ratio,format}` | 40004/40005/40006 |
| POST | /api/generate | `{resumeId, pageOption, watermarkMode, deepSearch}` | `{taskId}`；先跑提交关卡 | 40002/40003/40008 |
| GET | /api/task/{id} | — | `{state, progress, stage}` | 40008 |
| GET | /api/task/{id}/events | — | SSE 流（§4.4） | 40008 |
| POST | /api/task/{id}/cancel | — | `{canceled:true}` | 40008/40009 |
| POST | /api/projects/generate | `{resumeId, projectId?, mode}` | 单条项目 JSON | 40012 |
| POST | /api/projects/polish | `{resumeId, block, itemId, text}` | 美化后文本 | 50002 |
| GET | /api/projects/library | `?direction=` | 项目库条目列表 | — |
| POST | /api/skills/validate | `{skills, jobs}` | `{score, verdict:pass\|weak\|block, reason}` | 50002 |
| POST | /api/skills/extend | `{skills, jobs, skillExtend:true}` | 扩展后技能列表 | 50002 |
| POST | /api/adjust | `{taskId, measurement, config}` | `{config, rewrites}`（§6） | 40009 |
| GET | /api/export/html | `?resumeId=&watermark=` | HTML 字符串 | 40010 |
| GET | /api/export/pdf | `?resumeId=` | PDF 文件（HTML 定稿后启用） | 40010 |
| GET | /api/search/mode | — | `{apiReady, deepAvailable, missing[]}` | — |
| POST | /api/search/deep | `{taskId, query}` | `{status, result?}`（限频/HITL） | 50003 |
| GET | /api/config | — | 脱敏配置 | — |
| PUT | /api/config | `{provider, apiKey...}` | `{masked}` | — |
| POST | /api/init/test | `{provider?}` | `{textOk, vision:{source, ok}}` | 50002 |

### 4.3 任务状态机

状态：`pending → analyzing → generating → building → done`；终态另含 `failed` / `canceled`。

| 转移 | 触发 | 说明 |
|---|---|---|
| create → pending | POST /api/generate 通过提交关卡 | 任务入队（串行） |
| pending → analyzing | 调度开始 | JD 分析 + 联网搜索 + 共享事实表 |
| analyzing → generating | 事实表就绪 | 分块生成（板块级进度） |
| generating → building | 全部分块产出 | 模板装配 + 适配闭环 |
| building → done | 适配收敛（≤3 轮） | 产出最终配置与 HTML |
| analyzing/generating/building → failed | 致命错误 | 板块级失败不置 failed，仅 block 降级 |
| analyzing/generating/building → canceled | 用户取消 | 串行环境下可安全中止 |

### 4.4 SSE 事件格式

`GET /api/task/{id}/events`，Content-Type `text/event-stream`。事件：

| event | data 结构 | 含义 |
|---|---|---|
| task.created | `{taskId, state:"pending"}` | 任务已创建 |
| task.stage | `{taskId, stage:"analyzing"\|"generating"\|"building", stageIndex, stageTotal}` | 阶段切换 |
| block.progress | `{taskId, block:"summary"\|"education"\|"internship"\|"projects"\|"skills"\|"honor", progress:0~1}` | 板块进度 |
| block.done | `{taskId, block, ok, degraded?}` | 板块完成（失败已隔离） |
| task.adjust | `{taskId, round, action:"over"\|"under", config}` | 适配轮次通知 |
| task.done | `{taskId, resumeId, config, html}` | 完成（前端可直接渲染） |
| task.failed | `{taskId, error:{code,message}}` | 失败 |
| task.canceled | `{taskId}` | 已取消 |

前端按板块固定权重渲染进度条（对标 MS-Agent 8 步风格）。

---

## 5. 生成引擎设计（§6.1.1 采纳项落地）

### 5.1 分层并行 DAG

```
第一层（并行，无 JD 依赖）：
  JD 分析 + 联网搜索 ──┐（产出共享事实表，供给第二层）
  自我评价生成 ────────┤
  教育排版（固定） ─────┤
  实习美化（有则做） ───┤
  技能分类优化 ────────┘
第二层（依赖 JD）：
  项目生成（N 条按 §3.5 硬性条数，板块内可并行/串行）
  技能拓展（skillExtend=true 时）
审阅层（降本）：
  仅对 critical/high 项与溢出场景复核，输出建议（§6.5），不自动全量重跑
```

- 调度：单任务串行执行（无并发队列），但**第一层内部按板块并发调用 LLM**（异步 await 并行）。
- 进度：板块粒度上报（§4.4），固定权重：JD 分析 15% / 自我评价 10% / 教育 5% / 实习 10% / 技能 10% / 项目 35% / 技能拓展 5% / 装配适配 10%。

### 5.2 共享事实表（factsheet）

JD 分析产出唯一事实源，所有板块统一引用（防矛盾）：

```json
{
  "version": "1.0",
  "direction": "AI Agent / LLM 应用",
  "identity": "intern",
  "pageOption": "one-page",
  "coreSkills": ["大模型推理部署", "RAG 检索增强", "Agent 开发"],
  "jdFocus": "智能体系统、RAG 知识库落地",
  "projectType": "智能体系统",
  "metricStyle": "性能提升 8%~15%（1 位小数）、延迟 100~200ms、支持数百 QPS",
  "quantity": {"internshipCount": 1, "projectCount": 2},
  "keywordCoverage": 0.75
}
```

写入 Prompt 组装上下文（§6.10 第 4~6 层），`factsheet.version` 参与缓存 key（§5.4）。

### 5.3 高精度预算协议（预算前置）

- **自估输出协议**：所有描述性板块（summary/internship/projects）生成结果必须为 JSON：
  `{"blocks":[{"text":"...","estimatedLines":N}], "meta":{...}}`——模型在正文后输出该板块按当前页面宽度/详略档的**预估渲染行数**。
- **校准表**：`data/calibration.json` 追加每次实测 `{blockType, detailLevel, pageWidth, estimatedLines, actualLines, ratio}`；预算校正系数 = 历史 `actual/estimated` 的中位数。
- **误差阈值**：单板块 `|actual−estimated|/estimated > 20%` 时触发一次预算修正（按校正系数调整后续板块预算，并上报 `task.adjust`）。
- **兜底**：模型自估+校准仍偏差时，由 §6 适配闭环（≤3 轮）收敛；宁可紧凑不可溢出（§6.7）。
- 默认模型 DeepSeek-V4-Flash（内部参考，成本低，不做轻量约束，可支撑多次估算/校准迭代）。

### 5.4 增量重生成与缓存

- **缓存 key**：`SHA256(blockType | inputHash | factsheet.version | rules.version | prompt.version | budget)`。
- **inputHash**：相关输入字段 JSON 规范化后的 SHA256。
- **JD 分析缓存**：`SHA256(Jobs[] | rules.jobs.version)`。
- **失效规则**：用户编辑锁定该板块（edited=true）→ 该板块缓存禁用；rules/prompt 版本变更 → 全量失效；预算档位变化 → 描述性板块失效。
- 重生成只重建目标板块（`/api/projects/generate`、`/api/projects/polish`），JD 分析与未变动板块缓存复用。

### 5.5 编辑锁定

- 用户手动修改某条内容 → 该项 `edited:true`，**criticality 强制为 critical** → 不可被裁剪/压缩/自动重写（错误码 40012）。
- "重新生成"按钮：用户显式确认后解锁该条（先备份原文，重新生成后 `edited:false`）。
- 内容层压缩只作用于 `ai-created / polished` 且非 edited 项。

### 5.6 模块级失败隔离

- 单板块：首次失败 → 重试 1 次（简化 Prompt）→ 仍失败输出简化版 `{"degraded":true, "text":"（待补充）..."}` + `block.done(degraded)`，整单继续。
- 搜索失败：降级为纯 LLM，相关处标 `【待联网核实】`（不阻塞）。
- 致命错误（事实表构建失败、模板缺失等）才置 `failed`。

---

## 6. 动态适配运行协议（P5 消费）

**分工**：后端产出内容与密度配置；**前端浏览器渲染后测量**（DOM 高度最接近打印效果），调用 `/api/adjust` 取调整方案，再应用；≤3 轮收敛。

```
building 阶段：
  1. 后端注入模板（占位符替换、空区块删除、照片位）→ 产出 HTML 字符串 + config（density=normal 基线、contentPlan 按 §6.7 一页/两页默认档）
  2. task.done 推送；前端渲染预览 → adapt.js 测量（末页填充度 / 是否溢出）

适配闭环（前端主导，≤3 轮）：
  测量 → 判定：
    - 溢出（>100%）：action="over"
    - 不足（<75%）：action="under"
    - 75%~85% 可接受；≥85% 填满 → 收敛，结束
  → POST /api/adjust {taskId, measurement, config}
  → 后端 plan.py 按 §6.4 顺序决策：
      over：裁剪非常驻 low→medium → 主导板块内容层降档 → 合并项目要点 →
            精简自我评价（保留 critical）→ 排版层 density loose→normal→compact
      under：追加自我评价（至上限）→ 内容层升档 → density compact→normal→loose
    （均不增减项目条数 §3.5；不动 edited 项 §5.5）
  → 返回 {config, rewrites:{blockId: 新文本}}（rewrites 走增量重生成 §5.4，缓存复用）
  → 前端应用：仅切换 body[data-density] + 替换 rewrites 文本（复用 DOM，不重建）
  → 重测量；round ≥3 仍未收敛 → 优先保证不溢出（宁可紧凑），并 toast 提示可改选页数
```

阈值定稿（§6.7）：末页填充度 ≥85% 填满 / 75%~85% 可接受 / <75% 扩充 / >100% 压缩；两页版以第 2 页为准。

---

## 7. E2E 验收清单（P8 门禁，P6 起逐步可验）

| # | 验收点 | 通过标准 | 对应阶段 |
|---|---|---|---|
| E1 | 初始化引导 | 首启可配置密钥；能力检测（文本/视觉）结果分级提示；无死路 | P7 |
| E2 | 表单校验 | 教育 1~3、实习 0~2、JD 1~5 上限生效；时间/枚举/邮箱/电话拦截正确 | P2 |
| E3 | 提交关卡 | 技能相关性三档行为正确（0.3 阻止/0.3~0.6 提示/≥0.6 通过 + 关键词兜底）；跨领域拦截 | P2/P3 |
| E4 | 照片 | 格式/尺寸/大小/比例校验与提示正确；未传隐藏照片位 | P2 |
| E5 | 生成 | SSE 板块进度完整；项目条数符合 §3.5 映射（零漂移）；AI 创造/美化分支正确；数值直接生成且合理（抽查 5 项：无极端值、精度合规） | P4 |
| E6 | 预览编辑 | 编辑锁定生效（edited→critical）；单条重生成只影响目标板块；确认横幅展示 | P4/P6 |
| E7 | 适配 | 一页/两页末页填充度 ≥85%（或 75%~85% 可接受）；密度档全局生效；≤3 轮收敛；不溢出 | P5 |
| E8 | 导出 | 水印模式必选；AI 项确认清单未勾选阻止导出；练习/正式版正确；HTML 打印样式 ATS 合规；PDF（成熟后） | P6/P8 |
| E9 | 异常 | 板块失败降级"待补充"；搜索降级【待联网核实】；取消任务可中止；收敛失败提示改选页数 | P4/P6 |
| E10 | 回归 | 上述全链路在真实数据下无回归 | P8 |
| E11 | 配置体系（R18/R24 回流） | 多配置列表 + 激活优先级生效；厂商/模型下拉自动填充并隐藏 name/baseurl；Key 占位符随厂商+模型动态变化；存量自定义配置经 __custom 回显不丢数据；配置自检 401/429/404 等中文提示；搜索 Key 可开可关 | P7/P8 |
| E12 | 插件双层启动（R19/R21 回流） | 配置与启用分离；一键配置失败给出排查指引；启用回滚正确；OpenCLI / MediaCrawler（扫码提示）/ Agent-Reach / zhihu-cli / Tavily 可配置；功能模块开关联动 | P8 |
| E13 | 分发与体验（R17/R21/R25 回流） | 时间范围 2015.01~2030.12 前后端一致；便携 ZIP / 独立 EXE 自检通过；内置浏览器启动；左栏流程步骤联动 + 右栏聚焦说明（含动态行/按钮全覆盖）；可选分组默认收起、必选展开；MD / HTML 导出格式标准正确；Esc 关闭抽屉/弹窗；空列表有引导指引 | P8 |

---

## 8. M0 成功标准（本文档批准门禁）

1. 技术栈/目录结构无争议，P1 可直接照 §2 搭建；
2. §3 字段、枚举、校验规则完整且无歧义（前后端可独立实现）；
3. §4 接口/错误码/SSE/状态机完整，无未定义行为；
4. §5 采纳项设计（DAG/事实表/预算/缓存/锁定/隔离）可落地；
5. §6 适配分工（前端测量 + 后端决策）与 §7 验收清单无争议。
6. 用户评审批准（M0 通过）→ 进入 P1。

---

*本文档为 P0 契约稿。经用户批准后，按实施计划 P1 起逐步落地；契约变更需走 PRD/契约同步更新。*
