# 面试 HTML 生成规范（v2）

> 本文档是 `D:\TRAE\WORKSPACE\MS-Agent` 的**唯一操作手册**，整合全部机制：
> 目录分区、md→HTML 生成、多 provider 视觉分析自动切换、HTML 验证、面经实证闭环。
>
> 原则（用户确认版）：
> - **简历基准**：`10_知识库/简历基准/` 两个 PDF 是绝对权威，任何面试口径以 `参与边界卡.md` 为准；**两版二选一**——每家公司开始前由用户指定用了哪一份（A/B），材料只引用该版项目与数字
> - **面经实证**：单独分区 `10_知识库/面经实证/`，按"公司/岗位/精简JD/面试问题"沉淀，每次面试后更新
> - **岗位画像**：投递前用联网搜索 + 公开面经塑造，面试后反哺修正
> - **手撕题**：不体现在面试准备材料中（用户决定）
> - **不需要加密/保护**：文件明文存放，重点在"自动选择与切换方法"的健壮性

---

## 一、目录结构（固定，不可随意改动）

```
D:\TRAE\WORKSPACE\MS-Agent\
├── README.md                        # 总览导航（本规范的入口）
├── 00_规范\
│   ├── 面试html生成规范.md           # 本文档
│   ├── SOP.md                       # 标准作业程序（SOP-01~06 核心架构原则）
│   └── 多维度优化建议.md             # 多维度优化建议（已实施/建议）
├── 10_知识库/简历基准\                      # 绝对基准，禁止依赖其他来源
│   ├── AI开发工程师.pdf              # 简历 A 版（应用/Agent/RAG）
│   ├── AI推理部署工程师.pdf          # 简历 B 版（推理/部署/量化）
│   └── 参与边界卡.md                 # 项目边界 + 数字口径 + 红线（唯一权威）
├── 10_知识库/岗位画像\                      # 每家公司一个文件，联网+面经塑造
│   └── _模板-公司-岗位.md             # 模板；按 <公司>-<岗位>.md 命名新建
├── 10_知识库/面经实证\                      # 单独分区：真实面试记录
│   └── 面经实证库.md                 # 公司/岗位/精简JD/面试问题，含公开面经参考
├── 30_产出/面试材料\                      # 生成产物（HTML + 每家公司源 md）
│   └── <公司名>\
│       ├── 00_公司背景.md
│       ├── 01_自我介绍.md
│       ├── 02_项目深挖.md
│       ├── 03_技术场景题.md
│       ├── 04_反问环节.md
│       ├── 05_面经分析与面试题库.md
│       ├── 附录_数字口径.md
│       ├── .build-cache.json        # 增量构建缓存（sha256，勿手工改）
│       └── 面试准备.html            # build.js 产物
└── 20_执行\                           # 工具链（全部无第三方运行时依赖除 pdfjs-dist）
    ├── config.json                  # provider 配置（多 provider，cap 区分 text/vision 能力）
    ├── gen_material.js              # JD+简历版本 → 自动生成 7 个源 md → 自动 build+verify
    ├── vision_analyze.js            # 视觉分析：多 provider 自动选择 + 失败自动切换（cap=vision）
    ├── pdf_extract.js               # PDF 文本提取（pdfjs-dist v6 ESM）
    ├── build.js                     # md → HTML 生成器（v2 模板装配 + 增量构建，按公司目录参数化）
    ├── verify.js                    # HTML 验证（JS 语法 + 注入 + 标记 + 术语数 + SOP-CHECK）
    ├── glossary.js                  # 术语表共享模块（GLOSSARY/EXTRA，一次维护所有公司复用）
    ├── templates\skeleton.html      # HTML 静态骨架（CSS+DOM+渲染 JS，占位符注入）
    ├── components\                  # 通用内容组件库（intro 自我介绍框架 / star 项目 STAR 框架）
    ├── server.js                    # 本地预览服务器
    ├── ocr_js.js                    # 内置纯 JS OCR 引擎（本地离线识图，默认方案）
    └── node_modules\                # pdfjs-dist / mammoth / onnxruntime-node
```

---

## 二、内容生产流程（每次面试一家新公司）

### Step 0：指定简历版本（开始前，用户告知）
- 确认这家公司投的是 **A 版（AI开发工程师）** 还是 **B 版（AI推理部署工程师）**
- 后续所有源 md 只引用该版可讲的项目与数字，**另一版项目不得出现**（防止"投的 A 版却讲 B 版项目"穿帮）
- 生成时以第三参数注入版本标注：`node 20_执行\build.js <公司名> A` 或 `B`

### Step 1：建岗位画像（投递前）
1. 联网搜索：`<公司> <岗位> 招聘 JD`、`<公司> 面经 实习`
2. 在 `10_知识库/岗位画像/` 新建 `<公司>-<岗位>.md`，结构见 `_模板-公司-岗位.md` 模板：
   - 岗位定位 / JD 拆解→能力映射 / 公司与技术路线速记 / 匹配度（优势+劣势应对）/ 面试流程预期 / 来源链接
3. 只写可溯源信息，链接留档

### Step 2：写面试源 md（30_产出/面试材料/<公司>/）
两种方式，二选一：
- **自动（常用）**：`node 20_执行\gen_material.js <公司名> <A|B> <JD文件 | --jd="JD文本">`
  —— 读取参与边界卡（按版本）+ 岗位画像（若存在）+ JD，调用文本生成 provider 自动产出 7 个源 md 初稿，随后自动 build + verify。
  注意：生成的是初稿，必须人工复核（数字口径对照参与边界卡、项目边界、版本一致性）。
- **手动**：按 build.js 需要的固定文件名（`00_公司背景` 到 `附录_数字口径`），内容以 `参与边界卡.md` 为项目基准、以岗位画像为匹配主线。

### Step 3：生成 HTML 并验证
```powershell
# 生成（参数1=公司名，目录名需与 30_产出/面试材料 下子目录一致；参数2=简历版本 A/B）
# 增量构建：源 md 未变化时自动跳过渲染（SKIP）；内容有改动或首次构建才渲染
node 20_执行\build.js <公司名> <A|B>
node 20_执行\build.js <公司名> <A|B> --force   # 强制重建（调试用）

# 验证（JS 语法 + 数据注入 + 术语数 + 章节完整性 + SOP-CHECK 汇总）
node 20_执行\verify.js <公司名>

# 本地预览
node 20_执行\server.js   # 打开 http://127.0.0.1:8900
```

### Step 4：面试后更新面经实证（单独分区）
1. 在 `10_知识库/面经实证/面经实证库.md` 对应公司条目下，按轮次记录**真实问题**
2. 更新 `10_知识库/岗位画像/` 的匹配度与流程预期（反哺）
3. 若公开面经发现新考点，同步进 `30_产出/面试材料/<公司>/05_面经分析与面试题库.md`

---

## 三、build.js 机制（v2 模板装配模式）

- **输入**：`30_产出/面试材料/<公司>/` 下 7 个固定 md + `20_执行/glossary.js`（GLOSSARY/EXTRA 术语表，共享模块一次维护）+ `20_执行/templates/skeleton.html`（静态骨架）
- **输出**：同目录 `面试准备.html` + `.build-cache.json`（增量缓存）
- **增量构建**：对序列化源 md 取 sha256，与缓存比对；一致且产物存在 → `SKIP` 跳过渲染（0 开销）；`--force` 强制重建
- **模板装配**：读 `skeleton.html`（CSS+DOM+渲染 JS 一次维护），按 `{{COMP}}/{{RESUME_TAG}}/{{FILES_JSON}}/{{GLOSSARY_JSON}}/{{PHASES_JSON}}/{{BUILD_WARN_HTML}}` 注入内容，消除重复渲染同一框架的开销
- **阶段划分**（PHASES）：面试准备 → 自我介绍 → 项目经验 → 技术问答 → 反问环节 → 数字速查
- **术语 tooltip**：GLOSSARY（短解释）+ EXTRA（解释+高频追问+回答要点）合并注入，正文自动高亮
- **折叠**：含"追问防守/高频题/速补"等标题的章节自动折叠
- **参数化**：`node 20_执行\build.js <公司名> <A|B>`，公司名用于标题与导航；第三参数为简历版本（A/B），注入顶栏标注（如"简历 A 版 · 应用/Agent/RAG"），未指定则不显示
- **章节容错（P1-7）**：05 面经任一章节缺标题标记 → 跳过该段并记入 `SKIPPED`，HTML 顶部注入 `build-warn` 横幅，不阻断整体 build

## 三·B、gen_material.js —— JD+简历版本 → 自动生成面试准备（初稿）

**用途**：输入 JD + 简历版本，自动产出 `30_产出/面试材料/<公司>/` 下 7 个源 md 初稿，并自动执行 build + verify，实现"指定版本 + 提供 JD = 自动生成面试准备"。

```powershell
node 20_执行\gen_material.js <公司名> <A|B> <JD文件路径>        # JD 存于 txt/md 文件
node 20_执行\gen_material.js <公司名> <A|B> --jd="JD文本"        # JD 直接传文本
node 20_执行\gen_material.js --dryrun                            # 只检查配置
```

**机制**：
1. **输入**：`10_知识库/简历基准/参与边界卡.md`（按指定版本）+ `10_知识库/岗位画像/<公司>*.md`（若存在）+ JD
2. **生成**：对 8 个文件**限流并行**调用文本生成 provider（默认 3 并发，`MS_AGENT_CONCURRENCY` 可调；cap 含 text，fallback 链自动切换，60s 超时，max_tokens 超限自动减半降级），提示词强制"只用指定版本的项目与数字、不写手撕题"；`01_自我介绍` 按自我介绍框架（`20_执行/components/intro.js`）、`02_项目深挖` 按 STAR 框架（`20_执行/components/star.js`）固化结构
3. **兜底**：`01_自我介绍` 生成失败时用组件本地占位模板写盘（SOP-05），其余文件正常继续；无组件文件失败则标记 `failed` 并继续
4. **产出**：源 md 初稿 + 自动 `build.js`（增量构建）+ `verify.js`（SOP-CHECK），输出 `面试准备.html`
5. **注意**：LLM 输出是**初稿**，必须人工复核（数字口径对照参与边界卡、项目边界、版本一致性、build 章节标记）；生成失败会保留已写文件并提示修复；占位文件可在结果页「重试生成」覆盖

**已知约束**（2026-08 实测）：文本生成 provider 建议至少 2 个形成 fallback 链；免费小模型（如 glm-4-flash）输出短且生成慢，大规模长文生成建议配置更强文本模型（如 siliconflow Qwen 系列，填 apiKey）。

## 四、vision_analyze.js —— 多 provider 自动选择与失败自动切换

### 4.1 配置（config.json）

```json
{
  "providers": [
    {
      "name": "zhipu-vision",
      "baseUrl": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
      "model": "glm-4v-flash",
      "apiKey": "****",
      "enabled": true,
      "cap": ["vision"],
      "maxOutputTokens": 1024
    },
    {
      "name": "zhipu-text",
      "baseUrl": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
      "model": "glm-4-flash",
      "apiKey": "****",
      "enabled": true,
      "cap": ["text"],
      "maxOutputTokens": 4096
    }
  ]
}
```

- `providers` 为数组，**顺序即优先级**（自动选择 = 取第一个 enabled 且 apiKey 非空者）
- `enabled: false` 可临时停用某 provider，无需删除配置
- `cap`：能力标签，`["text"]`=文本生成、`["vision"]`=图片分析；不设置视为两者兼容。
  - `gen_material.js`（文本生成）只选 cap 含 `text` 的 provider
  - `vision_analyze.js`（图片分析）只选 cap 含 `vision` 的 provider
  - 建议每个能力至少配 2 个 provider，形成可靠 fallback 链（当前文本生成仅 zhipu-text 可用，建议补 siliconflow 等文本模型并填 apiKey）
- `maxOutputTokens`：该模型单次输出上限（视觉小模型常限 1024；超限时 gen_material.js 会自动减半降级重试）

### 4.2 自动选择与切换逻辑

```
调用 vision_analyze.js <image> [prompt]
  1. 读取 config.json → providers 数组
  2. 过滤出 enabled && apiKey 有效（长度>10）的 provider，按数组顺序排列
  3. 依次尝试：请求 → 成功则输出并退出
  4. 失败（网络错误 / 4xx / 5xx / 响应解析失败）→ 打印切换到下一家的日志，自动重试下一 provider
  5. 全部失败 → 汇总错误并退出码 1
```

- **无外网依赖**：仅用 Node 内置 `https`，无第三方包
- **超时控制**：每请求 30s 超时（防止单家卡死）
- **--dryrun**：只验证配置与图片存在性，不发请求

### 4.3 用途
面试材料中的图片/截图（如模型架构图、VLA 推理流程图）需要提取文字或描述时，用它做视觉分析补充进 md。

## 五、verify.js 验证机制

- **JS 语法**：提取所有 `<script>` 块用 `new Function` 检查
- **数据注入**：检查 `MD_FILES` / `GLOSSARY` / `PHASES` 是否存在
- **关键标记**：检查核心 DOM id 与函数是否齐全
- **术语数**：用**平衡括号扫描**解析 `const GLOSSARY = {...}`（非正则，规避超长 JSON 正则回溯问题——见 E 遗留修复说明），统计顶层键数
- **章节完整性**：按 REQUIRED_SECTIONS 白名单核对重组后各文件必备标题（缺标题即 FAIL）
- **组件框架（SOP-01）**：检查 `20_执行/components/` 注册组件（intro/star）的结构标记，缺失输出 WARN
- **SOP-CHECK 汇总**：结尾输出结构化检查点（SOP-01 组件框架 / SOP-02 构建流程 / SOP-03 术语表注入 / SOP-05 章节兜底），供发布审计

## 六、pdf_extract.js 说明

- 依赖 `pdfjs-dist` v6（ESM），用 `import()` 动态加载 `legacy/build/pdf.mjs`
- Windows 下 worker 路径必须转成 `file://` URL（`pathToFileURL`），否则报 "Only URLs with a scheme in: file, data, node"
- 用法：`node pdf_extract.js <pdf...>`

## 七、红线

1. `10_知识库/简历基准/` 的 PDF 与参与边界卡**不可被面试材料覆盖口径**——md 里出现数字前先查参与边界卡
2. `10_知识库/面经实证/` 只记真实问题，公开面经单独标注来源
3. 手撕题内容不写入面试准备材料
4. 生成/验证/预览必须走 20_执行 下的脚本，不手工改 HTML
