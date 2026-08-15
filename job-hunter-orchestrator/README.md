# job-hunter-orchestrator —— 自动求职系统"大脑"

LangGraph 总调度器骨架（MOCK 模式可端到端跑通），对应设计文档：
`D:\DSharnessWorkSpace\改造设计\0_大脑构造-LangGraph调度器设计.md` 与 `1_大脑Workflow详细设计-v0.1.md`

## 快速开始

```powershell
# 1. 安装依赖（首次）
cd D:\TRAE\WORKSPACE\job-hunter-orchestrator
python -m pip install -r requirements.txt

# 2. 启动 LangGraph Studio Web（或双击桌面「LangGraph Studio 启动器」）
langgraph dev --host 127.0.0.1 --port 2024

# 3. 浏览器打开 http://localhost:2024 → 左侧选择 job_hunter 图 → 运行
```

## 图结构（与设计文档 §1 对应）

```
START → parse_profile → check_profile ──缺失→ END(追问占位)
                                  └──完整→ resume_generate → match_jobs → gate_match
                                          ▲                                │
                                          │ pass: prep_materials → confirm_resume → track_jobs → final_report → END
                                          │ fail&未满: gap_analysis → resume_improve ──┘
                                          │ fail&已满: degrade_mark → prep_materials
```

## 目录结构

```
langgraph.json            # LangGraph 服务配置（Studio/CLI 读取）
requirements.txt
.env.example              # 复制为 .env：LLM/四项目 URL/RUN_MODE
graph\
  state.py                # JobHunterState 定义
  nodes.py                # 全部节点（MOCK 实现 + TODO 接入点）
  build.py                # StateGraph 装配 + 条件边路由
clients\
  api_client.py           # 四项目 HTTP 客户端（mock/real 开关）
```

## 骨架阶段说明

- `RUN_MODE=mock`：节点用模拟数据跑通全流程；模拟分数 55→67→79 演示反馈环收敛
- 真实接入：在 `clients/api_client.py` 实现各调用（参考 `改造设计/` 三份文档的 HTTP 契约），节点里替换 TODO 即可
- 人工确认点 `confirm_resume`：骨架版自动确认；真实版用 `interrupt()` + Checkpointer（见设计文档 §2 N9）
