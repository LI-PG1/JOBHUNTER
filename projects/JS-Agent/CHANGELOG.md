# 变更记录

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2026-08-11

### 新增
- LLM-Agent 核心循环（9 步编排：画像锚定 → 搜索规划 → 深度搜索 → 洗涤 → 收录判定 → 扩散 → 排序 → 清单生成 → 质检）
- 三层约束网关：Gate1 画像锚定（防幻觉 + 隐含技能补全）/ Gate2 采集收录（80/60/90 阈值 + 企业五档 + 时效）/ Gate3 输出质检（来源必填防编造）
- 控制台：15 家预设厂商、API Key 加密存储（DPAPI / Fernet）、约束强度三档、插件一键配置/卸载
- 多级回退搜索（智谱 → Tavily → DuckDuckGo → Playwright）与抓取（Jina → Trafilatura → urllib）
- 前端四步流程（配置 Key → 画像 → 匹配进度 → 结果清单）+ 空态/重试交互
- **Windows 打包版（PyInstaller）**：下载 zip 解压双击 exe 即用，免安装 Python/依赖
- GitHub Actions CI（Windows + Ubuntu × Python 3.10-3.12）

### 修复
- 企业类型过滤不生效（loop 未填充 enterprise_type）
- 隐含技能未参与匹配打分（与 missing 口径矛盾）
- 完全匹配岗位被 Gate3 误判（missing_skills=[] 判缺字段）
- "llm" 子串误命中 "vLLM"（词边界匹配）
- 搜索插件与组件面板状态脱节（ddgs 内置、Playwright 入链）

## [0.1.0] - 2026-07（废弃）

- 早期规则引擎原型（零 LLM 依赖）。已废弃，不提供支持。

---

计划中：v0.3（流式进度、并发抓取、评测集）。
