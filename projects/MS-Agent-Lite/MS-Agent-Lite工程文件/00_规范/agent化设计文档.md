# Agent 化演进设计文档（v2 · 产品规格版）

> 本文件是「面试助手Agent（MS-Agent）面试材料生成 Agent」的产品规格与实现蓝图。
> v2 依据最新产品规格重写：以**用户视角 6 步**为主线、以 **Agent 视角 7 项**为质量红线。
> 当前状态：M1 交互层 + 规格改造已全部落地并通过验证；M2~M4 为演进方向。
> 关联：[面试html生成规范.md](./面试html生成规范.md)（生成机制约定，本设计不破坏）。

---

## 一、产品定位

### 1.1 一句话

> 一个**用户自配 API + 本地插件的单机 Agent**：上传简历 + 填岗位 JD（可选补参考网址）→ 一键生成一份【岗位名称】面试准备.html。

### 1.2 用户视角 6 步（产品主线）

| 步骤 | 用户操作 | 界面提示（Agent 引导） |
|------|----------|------------------------|
| ① | 配置好需要的 API Key | 主面板第 1 步「大模型 API Key」：选平台自动填入或手动填写 + 能力选择（文本+视觉 / 多模态 / 文本+OCR）→ 保存并自检 |
| ② | 一键启动 | `npm start` → 浏览器打开 http://127.0.0.1:8900 |
| ③ | 在 web 对应位置上传简历 | 拖拽/点选，提示支持 **pdf / word(docx) / txt / markdown(md)**；提示"上传后生成将基于你的简历，含项目与数字" |
| ④ | 输入岗位名称 + 岗位 JD | 岗位名称提示"生成文件名为【岗位名称 + 面试准备】"；JD 支持文本粘贴或链接抓取（二选一） |
| ⑤ | 补充参考网址（可选，条数不限） | 可填公司官网 / 面经帖 / 技术文章 / 招聘平台 JD；添加即校验 http(s) 前缀并去重 |
| ⑥ | 一键生成 | 全程 SSE 实时进度（解析→抓取→生成 8 文件→渲染→校验→**内容审核**）→ 得到 **【岗位名称】面试准备.html** 并内嵌预览 |

### 1.3 Agent 视角 7 项（质量红线）

| # | Agent 能力 | 落地实现 |
|---|------------|----------|
| 1 | 每一步都有提示 | webUI 各输入区 label/hint/placeholder 全覆盖（apikey 接入、上传格式、哪些内容对生成有帮助、岗位名称命名规则） |
| 2 | 内置预设搜索分区 | `search_zones.js`：tech/AI/finance/ops/other 五类行业 → 常用检索网站映射，前端下拉选择即显示常用检索源 |
| 3 | 每一步都有对应内置 prompt | pipeline.js `FILES` 逐文件 hint + `buildSharedCtx` 硬性约束 + runCheck 审核 prompt（见 §四） |
| 4 | 对结果有审核 | `runCheck`：LLM 对照参与边界卡/上传简历审核数字口径、项目真实性、版本一致性 → PASS/WARN 展示在结果区 |
| 5 | 记忆与流程管理，避免信息丢失 | 完整上下文（含多 URL 抓取文本）落盘 `30_产出/面试材料/<岗位>/_上下文快照.md`；SSE 事件历史可重放；失败文件单文件重试不丢其余结果 |
| 6 | 系统适配 | 仅适配 **Windows**（PowerShell 5.1 执行策略/GBK 编码/中文路径已处理） |
| 7 | 分工明确 | 云端大任务（LLM 生成/审核，用户自配 API）；本地小任务（解析/抓取/渲染/校验/存储） |

### 1.4 非目标（本阶段不做）

- 多用户 / 登录鉴权
- Docker 化部署
- 对话式 Chat UI（列入 M2）
- 手撕题相关功能（红线：不写入材料）
- macOS / Linux 适配（当前仅 Windows）

---

## 二、总体架构

```
┌──────────────────────── 浏览器 · 任务式面板 UI（零构建原生 JS） ────────────────────────┐
│  输入区（简历上传 / 行业方向 / 岗位名称 / JD 文本或URL / 补充参考网址 x N）              │
│  过程区（任务状态 + 每文件 ✓/✗ + LLM fallback 链日志，SSE 实时推送）                     │
│  结果区（verify 徽标 + 内容审核 PASS/WARN + iframe 预览【岗位名称】面试准备.html）        │
│  设置区（provider 管理：新增/启停/自检 + 使用说明）                                      │
└──────────────────────────────────────┬──────────────────────────────────────────────────┘
                                       │ HTTP API + SSE（本地服务）
┌──────────────────────────────────────▼──────────────────────────────────────────────────┐
│  server.js（应用服务：静态托管 + API 路由 + SSE 通道）                                    │
│  ┌──────────────────────────────┐        ┌─────────────────────────────────────────────┐ │
│  │ pipeline.js（任务编排）        │        │ 本地插件（小任务）                           │ │
│  │  状态机 + 进度回调 + 取消      │───────▶│  parse_resume.js  pdf/docx/txt/md → 文本    │ │
│  │  urls 上下文 + 快照落盘        │        │  fetch_jd.js      URL → 文本（读取失败降级）    │ │
│  │  runCheck 内容审核（LLM）      │        │  build.js         md → 【岗位】面试准备.html │ │
│  └──────────┬───────────────────┘        │  verify.js        校验（沿用）              │ │
│             │ 云端（用户自配 API）          └─────────────────────────────────────────────┘ │
│  ┌──────────▼───────────────────┐        ┌─────────────────────────────────────────────┐ │
│  │ llm_gateway.js（多 provider） │        │ config_api.js + search_zones.js            │ │
│  │  cap 过滤/fallback/超时/降级  │        │  config.json 读写 / 行业→检索网站映射       │ │
│  └──────────────────────────────┘        └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**分工原则**：
- 云端（用户自配 API）：一切 LLM 调用（8 文件生成、内容审核 runCheck）
- 本地：文件解析（pdf/docx/txt/md）、URL 抓取、HTML 渲染、结构校验、静态服务、配置与行业预设存储

---

## 三、目标目录结构（当前实际）

```
MS-Agent\
├── README.md                          # 独立使用说明（v2 同步）
├── 00_规范\
│   ├── 面试html生成规范.md            # 生成机制约定（不变）
│   └── agent化设计文档.md             # 本文件（v2）
├── 10_知识库/简历基准\ 10_知识库/岗位画像\ 10_知识库/面经实证\   # 数据层（不变；03 有通用 _模板-公司-岗位.md）
├── 30_产出/面试材料\<岗位名称>\            # 生成产物：*面试准备.html + 8 源 md + _上下文快照.md
├── 20_执行\
│   ├── config.json                    # provider 配置（apiKey 脱敏存储）
│   ├── llm_gateway.js                 # 多 provider 网关（cap 过滤/fallback/超时/降级）
│   ├── pipeline.js                    # 生成管线编排：FILES 模板、buildSharedCtx、runCheck
│   ├── build.js                       # md → 【岗位名称】面试准备.html
│   ├── verify.js                      # 结构校验（JS 语法/数据注入/关键标记/术语数）
│   ├── search_zones.js                # 行业预设搜索分区（tech/ai/finance/ops/other）
│   ├── parse_resume.js                # 简历解析 pdf/docx/txt/md
│   ├── fetch_jd.js                    # URL 读取（UA/超时/重试/读取失败降级）
│   ├── config_api.js                  # config.json 读写 + 连通性自检
│   ├── gen_material.js                # CLI 薄包装（保留原参数签名）
│   ├── server.js                      # 应用服务（静态 + API + SSE）
│   └── web\
│       ├── index.html                 # 任务式面板（含样式，单页零构建）
│       └── app.js                     # 前端逻辑（fetch/SSE/状态渲染/审核展示）
└── package.json                       # 依赖：pdfjs-dist + mammoth（其余 Node 内置）
```

---

## 四、模块设计

### 4.1 `llm_gateway.js`（云端，多 provider 网关）

- 导出：`askText(prompt, {cap, maxTokens, onLog})`、`availableProviders()`、`listProviders(cap)`
- 行为：cap 过滤（text/vision）、顺序即优先级、失败自动切换、30s/60s 超时、max_tokens 减半降级
- 配置：`config.json` 数组，`enabled + hasKey + cap` 才可用

### 4.2 `pipeline.js`（任务编排 + 每步内置 prompt + 审核 + 记忆）

核心导出：

```js
runGenerate({ company, resumeVer, resumeText, jdText, urls }, { onProgress, signal })
  → Promise<{ ok, files, build, verify, check }>
retryFile(input, fileName, handlers)
```

- **每步内置 prompt**：`FILES` 数组为 8 个源文件定义 hint（章节标题严格对齐 build.js 的 slice 标记）；`buildSharedCtx` 组装：角色 → 硬性约束（只用参与边界卡/上传简历的项目与数字、不写手撕题）→ 岗位名称 → 简历版本 → JD → 参与边界卡 → 上传简历文本（**本次的权威简历**，冲突以简历为准）→ 补充参考网址（仅作参考，禁止照搬为经历）→ 岗位画像
- **记忆管理**：完整上下文落盘 `_上下文快照.md`（任务中断/重试不丢信息）；SSE 事件历史重放；单文件失败不阻断其余
- **结果审核 `runCheck`**：对照参与边界卡/上传简历检查 `01_自我介绍/02_项目深挖/附录_数字口径` 三文件 → 数字口径（是否出现基准外数字）、项目真实性（基准外项目/模型名）、版本一致性 → 首行 PASS 或 WARN+逐条建议
- 状态机：`parsing → fetching → generating(8) → building → verifying → checking → done|failed`

### 4.3 `build.js`（本地）

- 输出文件名：`<岗位名称>面试准备.html`（如 `腾讯-Agent开发实习生面试准备.html`）
- 章节标记对齐：`slice`/`sliceF`（分隔线缺失容错）
- 公司背景：优先读 `10_知识库/岗位画像/<岗位名>*`，缺失回退通用占位模板（已中立化，无特定公司绑定）

### 4.4 `verify.js`（本地）

- 目录扫描：`30_产出/面试材料/<岗位名>/` 下 `*面试准备.html`
- 校验项：内嵌 script 语法 / MD_FILES、GLOSSARY、PHASES 注入 / 关键功能标记 / 术语数（平衡括号扫描）

### 4.5 `search_zones.js`（Agent 预设搜索分区）

- `ZONES`：tech（程序员/开发）、ai（AI/算法/大模型）、finance（会计/财务/审计）、ops（运维/系统）、other（通用）
- 每区含 `prompt`（搜索策略）与 `sites`（常用检索网站数组，如 GitHub/牛客/CSDN/arXiv/国家税务局…）
- 前端下拉选择即显示常用检索源；`prompt` 供后续 M2 搜索 Agent 使用

### 4.6 `server.js`（应用服务）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/material` | 创建任务：解析上传简历 → JD 抓取（如为 URL）→ **循环抓取补充参考网址（逐条尽力，支持前端已抓 `{url,text}`）** → runGenerate |
| GET  | `/api/task/:id` | 任务状态 + 文件进度 + 结果（轮询兜底） |
| GET  | `/api/task/:id/events` | SSE：`step/file/log/build/verify/check/done/error` |
| POST | `/api/task/:id/cancel` | 取消（AbortController） |
| POST | `/api/task/:id/retry-file` | 单文件重试（透传 urls） |
| GET  | `/api/companies` | 已有公司/岗位历史（扫描 `*面试准备.html`） |
| GET  | `/api/search-zones` | 返回行业预设分区 |
| GET/POST | `/api/providers` (+ /test /:name DELETE) | provider 管理 |
| GET  | `/preview/<岗位>/<岗位>面试准备.html` | 预览 |

### 4.7 前端 `web/`（任务式面板）

1. **输入面板**：简历上传（拖拽/点选 + 格式与价值提示 + 解析预览）；行业方向下拉（显示常用检索网站）；岗位名称（命名规则提示）；JD 文本/链接二选一；补充参考网址（添加/去重/删除，条数不限）
2. **过程面板**：任务徽标 + 8 文件 ✓/✗/转圈 + SSE 日志（provider fallback 链）+ 取消/重试
3. **结果面板**：verify 徽标 + **内容审核 PASS/WARN 展示区** + iframe 预览 + 重试区
4. **设置抽屉**：使用说明（①填 OpenAI 兼容接口→保存 ②配置自检 ③需 enabled+cap 含 text）+ provider 列表管理 + 新增表单 + 状态提示

---

## 五、API 契约细节（POST /api/material）

```jsonc
// 请求
{
  "company": "腾讯-Agent开发实习生",   // 必填：岗位名称（生成 <岗位名称>面试准备.html）
  "resumeVer": "",                       // 可选：'A' | 'B' | ''（''=以上传简历为准）
  "resumeFile": "data:application/pdf;base64,....",  // 可选：base64 上传
  "jdText": "【岗位】...",                // jdText / jdUrl 至少其一
  "jdUrl": "https://.../job_detail/xxx.html",
  "urls": ["https://...面经帖", "https://...公司官网"]  // 可选：参考网址数组（条数不限）
}
// 响应
{ "taskId": "a1b2c3" }
```

SSE 事件序列（一次成功任务）：

```
event: step   {"name":"parsing","status":"running"}            → 解析上传简历
event: step   {"name":"fetching","status":"running"}           → 抓取 JD/参考网址（逐条 log）
event: log    {"text":"参考网址抓取完成：成功 2/3"}
event: step   {"name":"generating","status":"running"}         → 逐文件生成（8 file 事件 + fallback log）
event: step   {"name":"building","status":"done"}
event: step   {"name":"verifying","status":"done","detail":"RESULT: PASS"}
event: step   {"name":"checking","status":"done"}              → LLM 内容审核
event: done   {"previewUrl":"/preview/<岗位>/<岗位>面试准备.html","verify":true,"check":true,"checkOutput":"PASS\n..."}
```

---

## 六、错误处理与恢复

| 场景 | 处理 |
|------|------|
| 全部 provider 失败 | 任务 failed，前端给出配置指引（去设置页自检） |
| 单文件 LLM 失败 | 标记 failed 继续其他文件；前端「重试该文件」 |
| build 失败（章节标记缺失） | 列出缺失标题；sliceF 已容错分隔线缺失；M3 升级自动修复 |
| verify FAIL | 展示失败项；不阻塞预览，徽标红色 |
| URL 信息读取失败 | fetch_jd 返回可读提示，前端切"直接粘贴" |
| 参考网址读取失败 | 逐条尽力，失败仅 log 跳过，不阻断任务 |
| 内容审核失败/异常 | 仅告警（WARN 或跳过日志），不阻断整体结果 |
| 用户取消 | AbortSignal 中止 LLM 与子进程，任务 cancelled |
| 上传解析失败 | 前端即时报错，提示支持 pdf/docx/txt/md |

---

## 七、依赖变更

| 包 | 用途 | 状态 |
|----|------|------|
| pdfjs-dist | PDF 提取 | 已有 |
| mammoth | docx → 文本 | 已加 |
| @napi-rs/canvas | （疑似备用） | 已有 |

其余全部 Node 内置模块（http/fs/https/zlib/fetch）。

---

## 八、里程碑与验收

### M1 交互层 + 产品规格（✅ 已落地）

- [x] `llm_gateway.js` 多 provider 网关（cap 过滤/fallback/超时/降级）
- [x] `pipeline.js`：状态机 + 回调 + 取消 + 单文件重试 + urls 上下文 + `_上下文快照.md` + `runCheck` 审核
- [x] `build.js` / `verify.js`：新命名【岗位名称】面试准备.html + 目录扫描适配
- [x] `search_zones.js` 行业预设搜索分区 + `/api/search-zones`
- [x] `server.js`：/api/material 多 URL 抓取、/api/task SSE、/preview、providers、companies
- [x] 前端面板：简历上传（格式提示）/行业下拉/岗位名称/JD 双入口/参考网址管理/审核展示/设置说明
- [x] 中立化：无特定公司绑定，03 岗位画像通用模板
- [x] 独立 README + 端到端验证（语法检查、API 冒烟、生成产物）

### M2 Agent 编排（后续）

- [ ] 对话式指令入口（意图解析复用云端 API）
- [ ] 按 search_zones 的 prompt 驱动的联网搜索 Agent（自动抓面经/公司动态回填画像）
- [ ] 面经实证回填技能、岗位画像更新技能
- [ ] Critic 自修复：build 失败自动补章节标记重跑；审核 WARN 自动重生成相关文件

### M3 Agent 增强（后续）

- [ ] 版本一致性强校验（审核从"告警"升级为"阻断/自动修正"）
- [ ] 多 Agent 分工（生成/校验/搜索 Agent）
- [ ] 跨岗位会话记忆（生成历史档案可检索）

### M4 打磨部署（后续）

- [ ] 响应式与暗色模式、导出 PDF/打印
- [ ] provider 管理完善（额度统计/自动限流）
- [ ] Docker 化 / 非 Windows 适配

---

## 九、兼容性红线（实施时不可破坏）

1. 现有 CLI 命令全部保持可用（`gen_material/build/verify/server` 参数签名不变）
2. `10_知识库/简历基准` 参与边界卡仍为唯一权威；**上传简历为本次权威简历**（冲突以简历文本为准并核对数字口径）；生成提示词强制"只用指定版本项目与数字，禁止编造"
3. 生成/验证/预览必须走 20_执行 下脚本，前端通过 API 走同一逻辑，不绕行
4. `config.json` 格式向后兼容（旧配置无需迁移）
5. 补充参考网址仅作生成参考，**禁止照搬为候选人经历**（prompt 明确约束 + 审核要点覆盖）

## 十、开放问题

- 上传简历定位：当前为"权威简历"（冲突以简历为准）；是否进一步"生成新参与边界卡"列入 M3
- docx 解析默认 mammoth vs 零依赖手写（如需零依赖可替换）
- 预览 iframe 与本地 file:// 冲突：一律通过 `npm start` 访问 http://127.0.0.1:8900
