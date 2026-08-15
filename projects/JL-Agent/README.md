# 简历生成助手

> 你好，欢迎使用简历生成助手——一个把「个人背景 + 目标岗位 JD」变成定制简历的小工具：填写基本信息与经历、粘贴 JD，点一次按钮，即可得到排版完整、面向该岗位优化的简历（HTML / PDF / Word / Markdown），全程数据只保存在你本机。使用中如有任何问题或建议，欢迎联系我：[llxstupg@163.com](mailto:llxstupg@163.com)。也欢迎提出建议和问题——真诚的产品反馈有机会让你成为本项目的一员共创者，一起把简历生成助手做得更好。

> **📌 版本：v0.6.1（R30，2026-08-09，品牌与模型校正：产品显示名「简历生成助手」+ DeepSeek 真实模型名 v4-flash/v4-pro + 分页布局修复）**

## ✨ 它能做什么（结果一览）

```
📝 个人背景（基本信息 / 教育 / 实习 / 项目 / 技能 / 荣誉，本地输入）
🎯 目标岗位 JD（1~5 套，同一职业方向，可选联网搜索增强）
        │
        ▼  点一次「🚀 生成简历」，自动调用你配置的大模型 API
📄 【姓名】个人简历.html —— 一页 / 两页版，动态适配填满页面，可打印可导出
   PDF / Word / Markdown，另附 AI 生成内容确认清单
```

- 全程 Web 面板操作：SSE 实时进度、失败可重试、多 Provider 失败自动切换
- 数据留在本地：所有内容基于你填写的数据与自配 API，明文可查

## 🚀 三步开始（新手上路）

> 详细部署与更新流程见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)；独立 EXE 安装见 [docs/EXE_GUIDE.md](docs/EXE_GUIDE.md)。

1. **准备环境**：Python 3.10+，`python -m venv .venv` 后激活，再 `pip install -r requirements.txt`
2. **配置密钥**：`cp .env.example .env` 填入 API Key（默认 DeepSeek，支持任意 OpenAI 兼容接口）；可选 `cp config.example.json config.json` 调整模型 / 联网搜索
3. **启动**：

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000>，按页面引导填写资料与 JD，点「生成简历」即可。

> 💾 **免环境部署**：独立 EXE（Windows 10/11 双击即用）或便携 ZIP（内含嵌入式 Python，解压双击 bat），无需安装 Python——见 [docs/EXE_GUIDE.md](docs/EXE_GUIDE.md) / [portable/build_portable.py](portable/build_portable.py)

## 一、环境要求

| 项 | 要求 |
|----|------|
| Python | 3.10+（建议 3.12） |
| 操作系统 | Windows / macOS / Linux（EXE 版仅 Windows） |
| LLM API | 任一兼容 OpenAI 的文本模型 API（用户自备 Key） |
| 前端 | 原生 HTML/CSS/JS，无构建步骤 |

## 二、目录结构

```
JL-Agent\
├── app\                    # 后端（FastAPI 入口 / API / 核心校验 / 生成引擎 / 适配 / 搜索）
├── frontend\               # 前端面板（index.html + css + js，零构建）
├── templates\              # 简历模板（一页版 / 两页版，ATS 友好）
├── rules\                  # 规则文件（行业模板库 / 技能 / 项目 / JD）
├── docs\                   # 文档（PRD / 工程契约 / 部署 / 变更记录）
├── portable\               # 便携 ZIP 构建脚本
├── scripts\                # 版本检查等工具脚本
└── tests\                  # 冒烟 / 逻辑回归测试
```

## 三、常用命令

| 命令 | 用途 |
|------|------|
| `uvicorn app.main:app --host 127.0.0.1 --port 8000` | 启动面板（http://127.0.0.1:8000） |
| `python scripts\update_check.py` | 检查版本更新（对比 GitHub Release） |
| `.venv\Scripts\python.exe tests\smoke_api.py` | API 冒烟测试 |
| `.venv\Scripts\python.exe tests\logic_check.py` | 核心逻辑回归（133 项） |

## 四、常见问题

| 问题 | 处理 |
|------|------|
| 端口被占用 | 服务已在运行（直接访问 http://127.0.0.1:8000）；否则关闭占用 8000 的进程后重试 |
| 生成失败 / 任务报错 | 查看 SSE 进度与任务日志；确认 API Key 有效、余额充足；多 Provider 配置可自动切换 |
| 生成内容是否真实 | 数值为合理估算；AI 生成 / 美化内容带来源标记；导出前有 AI 内容确认清单；编辑锁定项不会被自动裁剪 |
| 中文乱码 | 终端请用 UTF-8；脚本内部统一 utf8 读写 |

## 五、授权与版权

本项目为作者（LinusLI）的原创创意成果，授权方式：**内部使用 / 待定**（LICENSE 详见仓库）。

> 证据链：GitHub 提交历史（创作时间戳）+ 项目内工程文档（设计决策过程）共同构成创意归属与创作时间的可追溯证据。

## 六、文档与版本

> **版本约定**：所有说明文档以本 README 顶部的版本号为准；功能变更需同步更新 README / [docs/CHANGELOG.md](docs/CHANGELOG.md)。

**文档清单**：

- [docs/PRD.md](docs/PRD.md)：产品需求文档（用户故事 + GWT 验收）
- [docs/contract.md](docs/contract.md)：工程契约（数据契约 / API 契约 / 引擎设计 / 验收清单）
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)：部署、环境配置、更新与发布流程
- [docs/EXE_GUIDE.md](docs/EXE_GUIDE.md)：独立 EXE 安装指南与 FAQ
- [docs/JL技术文档.md](docs/JL技术文档.md)：技术文档（设计思路 / 关键运行流程 / 升级路径）

**版本历史**（详见 [docs/CHANGELOG.md](docs/CHANGELOG.md)）：

- **v0.6.1（R30，2026-08-09）**：产品显示名统一「简历生成助手」；DeepSeek 改用真实 API 名（v4-flash / v4-pro，显示名/发送名分离）；分页布局修复（标题不孤悬页尾、防空白/防溢出、实习≥2 项目、技能分类收敛）
- **v0.6.1（R29，2026-08-09）**：导出前新增 AI 内容确认清单（强制勾选 + 水印模式必选展示）
- **v0.6.0（R22）**：仓库版版本机制 + 独立 EXE 分发方案
- **R25~R28**：三栏布局体验优化、导出支持 Markdown/HTML、UI/UX 与美术风格审核落地、致谢页脚
- **R21**：便携式自包含分发（嵌入式 Python 打包 ZIP + 双击 bat）
- **R19~R20**：插件双层启动机制（一键配置 + 功能模块精细控制）
- **R17~R18**：时间约束统一、高级设置抽屉（仿 MS-Agent）
- **R1~R16**：产品迭代与工程契约阶段（PRD / 数据契约 / API 契约 / 引擎设计，见 [docs/contract.md](docs/contract.md)）
