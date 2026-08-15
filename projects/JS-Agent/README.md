# JS-Agent 岗位匹配助手（v0.2 · LLM-Agent 版）

基于 **LLM-Agent 架构**的岗位匹配助手：用户提供大模型 API Key，JS-Agent 为其配备 CLI / Prompt / Skill，让大模型自主完成**深度搜索、数据洗涤、匹配判定、自我审查、清单生成**。核心是搜索与判断。

> 开源协议：MIT · 环境要求：Python ≥ 3.10（Windows / Linux / macOS）

## 特性

- 🧠 **LLM-Agent 架构**：用户 Key 驱动，大模型 + 三层约束网关完成搜索与判断
- 🚪 **三层约束网关**：Gate1 画像锚定（防幻觉）/ Gate2 采集收录（80/60/90 阈值 + 企业五档 + 时效）/ Gate3 输出质检（来源必填防编造）
- 🔍 **多级回退搜索**：智谱 web_search → Tavily → DuckDuckGo（免 Key）→ Playwright 兜底；抓取：Jina Reader → Trafilatura → urllib
- 🏢 **企业五档分类**：央企 / 国企 / 大型 / 中型（独角兽归此）/ 小型
- 🔐 **Key 加密落盘**：Windows 系统 DPAPI / 其他平台 Fernet，磁盘永不存明文
- ⚡ **四步流程**：配置 Key → 填写画像 → 执行匹配（实时进度）→ 查看清单（md / HTML）
- 🧩 **插件双按钮**：一键配置 / 一键卸载，配置中自动置灰

## 快速开始

### 方式一：Windows 打包版（免安装，双击即用）

下载 `js-agent-win64.zip` → 解压 → 双击 `js-agent.exe` → 浏览器自动提示打开 http://127.0.0.1:8101

无需安装 Python / 依赖。首次使用在页面控制台配置大模型 API Key 即可。

> 说明：打包版内置 DuckDuckGo / urllib 搜索通道；如需 Playwright 等扩展组件，请使用源码方式运行。
> 打包版数据（Key 加密存储、结果文件）保存在 exe 同级目录，删除 exe 目录即完全卸载。

### 方式二：源码运行

```bash
# 1. 克隆
git clone <你的仓库地址>
cd JS-Agent

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动（二选一）
python run.py              # 推荐：一键启动（打印使用提示）
# 或
uvicorn app.main:app --host 127.0.0.1 --port 8101

# Windows 也可直接双击 start.bat
```

浏览器打开 http://127.0.0.1:8101

## 使用流程（四步）

1. **配置 API Key**：控制台选择预设厂商（15 家）→ 填写模型与 Key → 一键连通性测试。Key 加密落盘，不存明文。
2. **填写画像**：教育 / 实习 / 项目 / 技术栈 / 城市 / 目标公司类型。
3. **执行匹配**：Agent 自动执行 9 步循环（画像锚定 → 搜索规划 → 深度搜索 → 数据洗涤 → 收录判定 → 扩散 → 排序 → 清单生成 → 质检），页面实时显示进度。
4. **查看结果**：md / HTML 清单（技能线标注、JD 拆解、投递动作、来源链接）。

## 核心机制

| 机制 | 说明 |
|------|------|
| 预设厂商 | 15 家（DeepSeek-V4-Flash/Pro、GLM、GPT-4o-mini、Qwen-Max、ERNIE、Doubao、Hunyuan、Kimi、MiniMax、Step、MiMo、Claude、Gemini、Ollama 本地、OpenAI 兼容模板），不允许自定义 |
| 匹配阈值 | ≥80% 收录 / 60-80% 补足 / <60% 淘汰 / ≥90% 自动扩散搜索 |
| 技能匹配 | 按技能本体 id 匹配（非名称字符串），ASCII 词条词边界匹配避免误命中 |
| 约束强度 | strict / standard / loose 三档（匹配阈值、时效、来源类型数可调） |
| JD 深度拆解 | 浅判（搜索摘要）→ 对候选岗位抓取正文精化（≤1500 字）→ 深判；灰区招聘平台不自动抓取 |

## 模型命名规范

**显示用通用命名，请求用官方 API 名**：界面、配置项、结果清单中一律显示左侧「通用显示名」；发送请求时由 `model_map` 自动转换为右侧厂商官方 API 模型名。以下映射均为各厂商公开信息，随官方迭代同步维护（代码位置：[app/config.py](app/config.py)）。

| 厂商 | 通用显示名（界面展示） | 官方 API 名（请求发送） |
|------|------------------------|--------------------------|
| DeepSeek | DeepSeek-V4-Flash | `deepseek-v4-flash` |
| DeepSeek | DeepSeek-V4-Pro | `deepseek-v4-pro` |
| 智谱 GLM | GLM-4.7-Flash | `glm-4.7-flash` |
| 智谱 GLM | GLM-4V-Flash | `glm-4v-flash` |
| 智谱 GLM | GLM-5 | `glm-5` |
| OpenAI | GPT-4o-mini | `gpt-4o-mini` |
| OpenAI | GPT-4o | `gpt-4o` |
| 阿里通义 | Qwen-Max | `qwen-max` |
| 阿里通义 | Qwen-Plus | `qwen-plus` |
| 百度文心 | ERNIE-4.0-Turbo | `ernie-4.0-turbo-8k` |
| 百度文心 | ERNIE-5.1 | `ernie-5.1` |
| 字节豆包 | Doubao-Seed-2.1-Pro | `doubao-seed-2-1-pro-260628` |
| 字节豆包 | Doubao-Seed-2.1-Turbo | `doubao-seed-2-1-turbo-260628` |
| 腾讯混元 | Hunyuan-TurboS | `hunyuan-turbos-latest` |
| 月之暗面 Kimi | Kimi-K2.6 | `kimi-k2.6` |
| 月之暗面 Kimi | Kimi-K3 | `kimi-k3` |
| MiniMax | MiniMax-M2.7 | `MiniMax-M2.7` |
| MiniMax | MiniMax-M3 | `MiniMax-M3` |
| 阶跃星辰 | Step-3.5-Flash | `step-3.5-flash` |
| 阶跃星辰 | Step-3.7-Flash | `step-3.7-flash` |
| 小米 MiMo | MiMo-V2.5-Pro | `mimo-v2.5-pro` |
| Anthropic | Claude-Sonnet | `claude-sonnet-4-5` |
| Anthropic | Claude-Haiku | `claude-haiku-4-5` |
| Google Gemini | Gemini-2.5-Flash | `gemini-2.5-flash` |
| Ollama（本地） | Qwen2.5 | `qwen2.5` |
| Ollama（本地） | Llama3.1 | `llama3.1` |

> OpenAI 兼容（预置模板）不预置 model_map：模型名按用户网关配置填写，不做转换。
> 规范约束由测试保障：`tests/test_llm.py::test_all_providers_have_model_map` 强制每个显示名必须映射官方 API 名，防止再次出现「显示名直接发请求」导致的 400 错误。

## 技术栈

FastAPI + Uvicorn · 原生 HTML/CSS/JS 前端 · OpenAI 兼容 LLM 协议 · 技能本体规则库（JSON Schema 校验）· pytest 测试

## 隐私与安全

- 大模型 API Key **仅存本地**：Windows 用系统 DPAPI 加密；Linux/macOS 用 Fernet（密钥在 `~/.js-agent/secret.key`，0600 权限）。`storage/keys.json` 已被 .gitignore 排除，**绝不提交**。
- 搜索请求从你的设备直接发出，JS-Agent 不收集、不上传任何数据。

## 免责声明

- 搜索通道包含非官方源（DuckDuckGo 免 Key 解析、Jina Reader 等），**仅供个人学习与研究**，请遵守目标网站服务条款，勿用于高频抓取。
- 匹配结果由大模型判断 + 规则网关约束生成，可能存在误差，投递前请以招聘方官方信息为准。

## 常见问题（FAQ）

**Q：没有大模型 API Key 能用吗？**
A：不能执行匹配（匹配判断依赖 LLM）。但可先用 DuckDuckGo 等搜索通道验证岗位检索效果；支持 Ollama 本地模型作为零费用替代。

**Q：Linux 上提示 cryptography？**
A：非 Windows 平台需要 `cryptography` 加密 Key，`pip install -r requirements.txt` 已包含；密钥文件会自动生成到 `~/.js-agent/`。

**Q：如何添加更多技能/岗位/行业？**
A：编辑 `rules/` 下对应本体 JSON（参考现有格式），Schema 校验保证格式正确。

**Q：结果文件在哪？**
A：`storage/` 目录下（已被 git 忽略）。前端页面也会展示结果。

## 架构

```
JS-Agent/
├── app/
│   ├── main.py          # FastAPI 入口（/api + 静态前端）
│   ├── config.py        # 预设厂商 15 家 + 约束强度 + 跨平台 KeyStore
│   ├── core/            # 规则库 / 三层网关 / 企业五档 / LLM 客户端 / 错误定义
│   ├── agent/           # Agent 主循环（9 步编排）/ 搜索规划 / 系统 Prompt
│   ├── plugins/         # 通用插件（search / fetch / scrub / writer + 自动部署）
│   └── api/             # 路由（match 异步任务 / console 控制台）
├── rules/               # 核心规则库（schema 校验 + 本体 + 种子岗位）
├── frontend/            # 四步流程单页 + 悬浮控制台
├── storage/             # 运行时数据（keys.json 加密、结果输出，git 忽略）
├── tests/               # pytest（网关 / 企业分类 / LLM 客户端 / API 冒烟）
├── docs/                # PRD / 设计方案 / 测试报告
├── run.py / start.bat   # 一键启动
└── .github/workflows/   # GitHub Actions CI（双平台自动测试）
```

## 测试

```bash
pip install pytest
pytest tests -q          # 50 个用例：三层网关 / 企业分类 / LLM 客户端（mock，含 model_map 命名规范）/ API 冒烟 / Key 加密
```

## 构建 Windows 打包版

```bash
pip install pyinstaller
python -m PyInstaller js-agent.spec --noconfirm --distpath dist --workpath build
# 产物：dist/js-agent/（压缩为 zip 分发）
```

## 文档

- [PRD](docs/PRD.md) · [LLM-Agent 设计方案](docs/设计方案_LLM-Agent版.md) · [测试报告](docs/测试报告_v020_端到端.md)
- [变更记录](CHANGELOG.md) · [参与贡献](CONTRIBUTING.md)

## 开源协议

[MIT License](LICENSE)
