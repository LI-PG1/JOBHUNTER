# JobHunter —— LangGraph 多 Agent 改造工作空间

> 工作空间：`D:\TRAE\WORKSPACE\JobHunter`
> 用途：对 JL-Agent / JS-Agent / MS-Agent-Lite 三个子项目做 LangGraph 化改造并并入大脑（job-hunter-orchestrator），形成 LangGraph 多 Agent 调度结构。

## 目录结构

```
JobHunter\
├── _设计文档\                 # 改造设计文档（副本，来自 D:\DSharnessWorkSpace\改造设计\）
│   ├── 0_大脑构造-LangGraph调度器设计.md
│   ├── 1_大脑Workflow详细设计-v0.1.md
│   ├── 3_总实施计划-v1.md
│   ├── 4_大改造架构设计-v2.0.md     ← 当前框架草案（待讨论定稿）
│   ├── JL-Agent_改造设计.md
│   ├── JS-Agent_改造设计.md
│   └── MS-Agent-Lite_改造设计.md
├── projects\                  # 四个项目工程文件副本（只读参考，源文件不动）
│   ├── JL-Agent\              # Python FastAPI（简历生成）
│   ├── JS-Agent\              # Python FastAPI（岗位匹配）
│   ├── MS-Agent-Lite\         # Node.js（面试材料）
│   └── interview-tracker-assistant\   # Node.js（面试跟踪，不改造）
└── README.md
```

## 使用规则

- **所有生成物（文档、代码、脚本）必须落在本工作空间内**，不溢出到其他目录。
- `projects/` 下是**源项目的副本**：改造一律基于副本进行，**不修改源项目文件**；需要新文件/新工程（如改造后的 Agent 图）在 `projects/` 对应目录或本空间新建。
- 各项目副本已排除运行时/构建产物（`.venv`、`dist`、`build`、`runtime`、`node_modules`、`output`、`storage` 等），保留纯工程文件与示例数据（MS-Agent-Lite 含 `30_产出/面试材料` 示例与 OCR 模型，供回路测试）。

## 源项目位置（勿动）

| 项目 | 源目录 | GitHub |
|---|---|---|
| JL-Agent | `D:\TRAE\WORKSPACE\JL-Agent` | LI-PG1/JL-Agent |
| JS-Agent | `D:\TRAE\WORKSPACE\JS-Agent` | LI-PG1/JS-Agent |
| MS-Agent-Lite | `D:\TRAE\WORKSPACE\MS-Agent-ALL\MS-Agent-Lite` | LI-PG1/MS-Agent-Lite |
| interview-tracker | `D:\TRAE\WORKSPACE\面试跟踪助手` | LI-PG1/interview-tracker-assistant |
| 大脑骨架 | `D:\TRAE\WORKSPACE\job-hunter-orchestrator`（M0 mock 已跑通） | — |
