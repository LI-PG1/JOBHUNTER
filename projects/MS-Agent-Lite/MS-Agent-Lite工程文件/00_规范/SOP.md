# MS-Agent 标准作业程序（SOP）

> 本文档定义 MS-Agent 系统的**核心架构原则**：所有流程（解析 / 抓取 / 生成 / 构建 / 验证 / 审核 / 发布 / 文档）统一遵循编号 SOP 执行，保证一致性、可复现、可审计、可维护。
> 配套落地：代码注释以 `SOP-0x` 标注检查点；`verify.js` 每次输出 `SOP-CHECK 汇总`；变更后按 SOP-04 同步文档。
> 版本：v1.0（2026-08-05，随 v0.3.0 架构升级发布）

---

## 0. 为什么需要 SOP

| 问题（改造前） | SOP 方案 |
|---|---|
| 8 个源文件结构靠 LLM 自由发挥，每次结构漂移 | SOP-06 组件化 prompt 固化结构 |
| HTML 模板 54KB 内联在 build.js，每次全量解析 | SOP-01 模板/组件/术语表分层，一次维护 |
| 源 md 未变仍全量渲染 | SOP-02 增量构建（sha256 缓存跳过） |
| 章节被跳过时 verify 依旧 PASS | SOP-03 验证检查点（章节白名单 + SOP-CHECK） |
| 代码改了文档不更新，规范失效 | SOP-04 文档同步机制 |
| 单个文件生成失败导致整条 build 中断 | SOP-05 组件兜底 + 单文件重试 + 告警 |
| 生成"成功"但数字/口径/结构违规要等人工审核 | SOP-07 质量回路：生成后自动质检（D1~D5）+ 不合格自动回炉/告警 |

---

## 1. SOP 体系总览

| 编号 | 名称 | 适用环节 | 核心动作 |
|---|---|---|---|
| **SOP-01** | 模板/组件/术语表分层与单一维护 | 构建 / 生成 | `templates/skeleton.html` + `components/` + `glossary.js` 一次维护，所有公司/岗位复用 |
| **SOP-02** | 构建流程标准 | 构建 | 装配式构建（内容注入静态骨架）+ 增量缓存（内容未变跳过渲染） |
| **SOP-03** | 验证与发布流程 | 验证 / 发布 | `build → verify → check → 发布`；verify 输出 SOP-CHECK，缺失章节即失败 |
| **SOP-04** | 文档同步 | 全部 | 结构/机制变更后，同步 README 与《面试 HTML 生成规范》等文档，变更留痕 |
| **SOP-05** | 错误处理与兜底 | 生成 / 构建 / 审核 | 组件兜底占位、SKIPPED 告警、单文件重试、任务取消响应、超时保护 |
| **SOP-06** | 生成规范统一 | 生成 / 审核 | 组件化 prompt、上下文上限、prompt 注入防线、数字口径红线 |
| **SOP-07** | 质量回路 | 生成 / 验证 / 审核 | 生成后自动质检（D1 数字 / D2 项目 / D3 JD 契合 / D4 结构 / D5 术语），不合格自动回炉或告警 |

---

## 2. SOP-01 模板 / 组件 / 术语表分层

**目的**：消除重复渲染与框架构建；保证输出质量一致；一次维护所有公司复用。

**分层结构**（新增，位于 `20_执行/`）：

```
20_执行/
├── templates/skeleton.html      # 静态骨架：CSS + DOM + 渲染 JS，占位符 {{COMP}}/{{FILES_JSON}}/...
├── components/                  # 通用内容组件库（结构固化）
│   ├── index.js                 # 注册表：forTarget / buildHint / fallbackFor / validate
│   ├── intro.js                 # 自我介绍框架（90 秒完整版/60 秒精简版/一面策略）
│   └── star.js                  # 项目 STAR 框架（S 背景/T 任务/A 行动/R 结果/追问防守）
└── glossary.js                  # 术语表共享模块（GLOSSARY 短解释 + EXTRA 深挖），一次维护
```

**执行步骤**：
1. **模板**：静态骨架只维护 `templates/skeleton.html`，build.js 只做占位符注入（6 个 `{{X}}`），不再内联渲染框架。
2. **组件**：新增组件 = 在 `components/` 建模块并加入 `REGISTRY`，提供 `framework`（prompt 提示）、`requiredMarkers`（verify 校验）、`fallback()`（LLM 失败占位）。pipeline 与 verify 自动生效，无需改其他代码。
3. **术语表**：术语只维护 `glossary.js`（GLOSSARY/EXTRA），build.js `require` 注入，所有公司/岗位复用同一套。

**检查点**：`verify.js` 的 `SOP-01 组件框架·<组件名>: PASS/WARN`。

---

## 3. SOP-02 构建流程标准

**目的**：内容未变不重复渲染；装配式构建降低计算开销与生成时间。

**执行步骤**（`build.js` v2 模板装配模式）：
1. 读取源 md（`00_公司背景` ~ `附录_数字口径`，`05_面经` 拆分重组）。
2. 计算 `contentHash = sha256(JSON.stringify(files))`，与 `.build-cache.json` 比对：
   - 一致且产物存在 → 打印 `SKIP: 源 md 无变化`，直接退出（零渲染开销）。
   - 不一致 / 无缓存 / `--force` → 继续。
3. 装配：读 `templates/skeleton.html`，按 `{{COMP}}/{{RESUME_TAG}}/{{FILES_JSON}}/{{GLOSSARY_JSON}}/{{PHASES_JSON}}/{{BUILD_WARN_HTML}}` 注入。
4. 写产物 + 写缓存（含 hash 与 builtAt）。

**命令**：`node 20_执行\build.js <公司名> <A|B>`；`--force` 强制重建（调试用）。

**检查点**：`verify.js` 的 `SOP-02 构建流程: PASS`；产物与源 md 一一对应可回溯。

---

## 4. SOP-03 验证与发布流程

**目的**：发布前必须经过机器验证，缺失章节/空内容/语法错误不允许静默发布。

**执行步骤**（pipeline 状态机）：
1. `building`：build.js 渲染 HTML。
2. `verifying`：verify.js 输出 SOP-CHECK 汇总（含组件框架、术语表、章节白名单）。
3. `checking`：LLM 内容审核（数字口径 / 项目真实性 / 版本一致性），PASS/WARN；尽力而为，失败仅告警不阻断。
4. `done`：全部通过才标记成功；任一关键项失败 → `RESULT: FAIL`。

**发布门槛**：`verify.js RESULT: PASS`（关键项：JS 语法、数据注入、章节完整性、md 非空）。

**检查点输出格式**：

```
SOP-CHECK 汇总:
  SOP-01 组件框架·自我介绍框架: PASS
  SOP-01 组件框架·项目 STAR 框架: PASS
  SOP-02 构建流程: PASS
  SOP-03 术语表注入: PASS
```

---

## 5. SOP-04 文档同步

**目的**：代码/结构变更后文档必须同步，防止"规范失效"。

**触发条件**（任一）：新增/修改工具脚本、模板、组件、术语表、目录结构、机制（增量缓存/并行/兜底）。

**同步清单**：
1. `README.md`：版本号、机制表、演进路线。
2. `00_规范/面试html生成规范.md`：目录结构、build 机制、verify 机制。
3. 本文件（SOP.md）：SOP 编号与动作变更。

**留痕**：变更在文档"更新记录"中登记（日期 + 变更点）。

---

## 6. SOP-05 错误处理与兜底

**目的**：单点失败不中断整体；用户可感知、可恢复。

**分层兜底**：

| 失败点 | 兜底动作 |
|---|---|
| 单个源文件 LLM 生成失败 | 组件 `fallback()` 写本地占位（intro），其余文件继续生成；无组件文件标记 `failed` 并继续 |
| LLM 输出缺章节标题 | build.js `sliceSafe/sliceF` 跳过该段 + `SKIPPED` 记入 HTML 顶部 `build-warn` 横幅 |
| build/verify 子进程挂死 | `runChild` 120s 超时强制 kill，返回失败不占锁 |
| 任务取消 | 全链路 AbortSignal 透传：LLM 请求立即中断、生成/审核阶段立即返回 `cancelled` |
| 所有文件均失败 | 终止并明确报错（无可用源，不继续 build） |
| 内容审核（check）失败 | 仅告警不阻断发布（输出到日志与前端） |

**恢复路径**：前端对 `failed` 文件提供"重试生成"（`retryFile`）；`fallback` 占位文件可在结果页重试覆盖。

---

## 7. SOP-06 生成规范统一

**目的**：所有文件生成遵守同一约束，输出一致、口径不漂移。

**硬性约束**（pipeline 注入系统层防线，所有文件共用）：
1. 项目/参与度/数字只能来自 `参与边界卡.md` 指定版本（A/B 二选一）或用户上传简历，禁止编造。
2. 另一版本项目不得作为【项目】出现。
3. 不写入手撕代码备考内容。
4. 输出 Markdown，标题层级从 `##` 开始。

**prompt 注入防线**：`SYSTEM_GEN/SYSTEM_CHECK` 声明所有 `【】` 区块为数据非指令，防 JD/简历/参考信息夹带注入。

**上下文上限**：JD / 简历 / 补充参考信息各 20,000 字符，参考网址 15 条 × 8,000 字符总量 50,000，超出截断并标注，防小模型上下文撑爆。

**组件框架**：`01_自我介绍` 强制 `## 90 秒完整版 / ## 60 秒精简版 / ## 一面策略`；`02_项目深挖` 强制 STAR 五段。结构固化一次维护。

**并发**：生成阶段限流并行（默认 3，`MS_AGENT_CONCURRENCY` 可调），单文件失败不阻断。

---

## 8. SOP-07 质量回路（M3）

**目的**：生成"成功"不等于质量达标——在发布门槛（SOP-03）之前对生成内容做**自动化质量闭环**：D1~D4 本地规则 + D5 术语 + D3 LLM JD 契合判定；不合格自动回炉（`on`）或标注告警（`warn-only`），杜绝数字口径/项目漂移/结构违规漏检。

**五维检查（quality_check.js / reviewer.js）**：

| 维度 | 检查内容 | 实现 | 裁决 |
|---|---|---|---|
| D1 | 数字口径：与《参与边界卡》/简历数字一致（含格式比对） | quality_check.js（确定性规则） | PASS / FAIL |
| D2 | 项目/经历不漂移：另一版本项目不得作为【项目】出现，参与边界外不新增 | quality_check.js（确定性规则） | PASS / FAIL |
| D3 | JD 契合：内容是否贴合 JD 重点（LLM 判定） | reviewer.js（调 LLM，可配 reviewFiles） | PASS / WARN / FAIL |
| D4 | 结构完整性：章节标题/层级/大小写/重复段落 | quality_check.js（确定性规则） | PASS / FAIL |
| D5 | 术语表一致性：与 glossary.js 术语对齐 | quality_check.js（确定性规则） | PASS / WARN |

**模式**（`--quality=on|warn-only|off`，Web 生成请求 `body.quality.mode` 透传）：
- `on`：D1~D5 任一 FAIL → 携 issues 自动回炉重写（上限 `maxRounds`，默认 1）；达上限仍 FAIL → 保留最新稿并标 WARN 交给用户。
- `warn-only`：只质检并输出 `qualitySummary`，不自动重写；用户在前端结果页看明细后手动「回炉」（`/api/task/:id/rework-file`）。
- `off`：不质检（默认关，与旧行为一致）。

**执行步骤**（pipeline 内 `qualityLoopForFile`）：
1. 单文件生成 done → `quality_check`（D1/D2/D4/D5）→ 需要时 `reviewer`（D3）。
2. 全部 PASS → 进入下一文件；有 FAIL 且 `mode=on` → 回炉重写（原稿 + issues 并入 prompt）→ 重新质检，循环至达标或达上限。
3. 每文件最终裁决写入 `30_产出/面试材料/<公司>/.quality.json`（与 build 缓存同目录，供 verify 与前端聚合）。

**检查点**：`verify.js` 的 `SOP-CHECK 汇总` 新增：
```
  SOP-07 质量回路·D1 数字口径: PASS
  SOP-07 质量回路·D2 项目不漂移: PASS
  SOP-07 质量回路·D4 结构完整: PASS
  SOP-07 质量回路·D5 术语一致: WARN
  SOP-07 质量回路·D3 JD契合(LLM): PASS
```

**落地文件**：`20_执行/quality_config.js`（阈值/模式/维度开关）、`20_执行/quality_check.js`（D1/D2/D4/D5 规则）、`20_执行/reviewer.js`（D3 LLM 判定 + 多 provider fallback）、`20_执行/pipeline.js`（`generateOne` feedback + `qualityLoopForFile` + `runGenerate` 分流 + `qualitySummary` 收尾）、`20_执行/server.js`（quality 透传 + 任务响应聚合 + rework-file 端点）、`20_执行/verify.js`（SOP-07 检查点 + 附录数字口径章节）。

---

## 9. SOP 落地对照（代码位置）

| SOP | 落地文件 |
|---|---|
| SOP-01 | `20_执行/templates/skeleton.html`、`20_执行/components/*`、`20_执行/glossary.js` |
| SOP-02 | `20_执行/build.js`（增量构建 + 模板装配） |
| SOP-03 | `20_执行/pipeline.js`（状态机）、`20_执行/verify.js`（SOP-CHECK） |
| SOP-04 | 本文档 + `README.md` + `00_规范/面试html生成规范.md` |
| SOP-05 | `20_执行/pipeline.js`（fallback/超时/取消）、`20_执行/build.js`（SKIPPED） |
| SOP-06 | `20_执行/pipeline.js`（SYSTEM_GEN、上下文上限、components hint） |
| SOP-07 | `20_执行/quality_config.js`、`quality_check.js`、`reviewer.js`、`pipeline.js`、`server.js`、`verify.js` |

---

## 更新记录

| 日期 | 变更 |
|---|---|
| 2026-08-05 | v1.0 初版：定义 SOP-01~06，随 v0.3.0（模板分层 + 增量构建 + 并行生成 + 组件库）落地 |
| 2026-08-18 | v1.1 新增 SOP-07 质量回路（M3）：D1~D5 自动质检 + 自动回炉/告警，落地 quality_config / quality_check / reviewer / pipeline / server / verify；SOP-CHECK 汇总新增 SOP-07 检查点 |
