# job-hunter-orchestrator —— 自动求职系统"大脑"

LangGraph 总调度器（mock 离线可跑，real 进程内三组件 + LLM），对应设计文档见 `_设计文档/`：
`0_大脑构造-LangGraph调度器设计.md`、`1_大脑Workflow详细设计-v0.1.md`、`4_大改造架构设计-v2.0.md`。

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
START → parse_profile → check_profile ──缺失&未满2轮→ check_profile(interrupt 追问用户)
                                  └──完整→ resume_generate → match_jobs → gate_match
                                          ▲                                │
                                          │ pass: build_submission_plan → confirm_resume(interrupt)
                                          │ fail&未满: gap_analysis → resume_improve ──┘
                                          │ fail&已满: degrade_mark → build_submission_plan
                                          │
                                          confirm_resume(N9 简历确认): 确认使用→prep_materials / 提修改→resume_improve / 拒绝→END
                                          prep_materials → track_jobs → final_report
```

> Q10 落地（2026-08-18）：`build_submission_plan` 在 N9 前置生成投递清单（消费四项输入：
> 简历解析 profile + city + max_results + company_types），N9 语义扩展为**投递确认**——
> interrupt 展示清单（只推荐不引导，投递由用户独立完成），确认后置 `confirmed`；
> 导出走 `export/submission_html.py`（复用用户范本格式，A4 横向可打印）。

### 日志（排查埋点）

- logger 名 `jobhunter.graph`，级别 INFO 起即可看到 Q10/N9 投递确认链路埋点（进入/过滤集合/剔除/截断/用户决定/分支结果）；宿主负责 `logging.basicConfig`（`run_full_e2e.py` 已配置，真实服务由 LangGraph 日志转发）。
- 注意：langgraph `interrupt` 节点函数会执行两次（首次构建 payload / resume 后重新执行），故 `N9 投递确认 进入` 每条场景打印 2 次属正常机制；`用户决定` 只在 resume 后打印 1 次。
- DEBUG 级别可看到各节点增量输出，排查状态透传问题。

## 目录结构

```
langgraph.json            # LangGraph 服务配置（Studio/CLI 读取）
requirements.txt
.env.example              # 复制为 .env：LLM Key + RUN_MODE（单仓库自包含，无外部服务）
run_full_e2e.py           # 全链路测试：模拟用户各阶段输入，生成测试报告（含 Q10e 导出 smoke）
graph\
  state.py                # JobHunterState 定义
  nodes.py                # 全部节点（组件化主线：进程内三组件 + 节点内确定性降级；含 Q10 build_submission_plan）
  build.py                # StateGraph 装配 + 条件边路由
export\
  submission_html.py      # Q10e 投递清单 HTML 导出（复用范本格式，纯确定性渲染）
clients\
  llm.py                  # 进程内 LLM（OpenAI 兼容直连，控制台 API Key 即时生效）
```

## 能力与运行模式

- **单仓库自包含**：clone 本仓库到本地即可使用完整功能——简历生成（resume_agent）、岗位匹配（match_agent）、面试材料（prep_agent）三组件进程内调用，投递跟踪（tracker_agent）本地 JSON 存储，**不依赖任何外部服务**。
- `RUN_MODE=mock`：组件 mock 后端 / 占位 LLM，本地全流程模拟，无需 Key 开箱即用；画像解析按 `user_goal` 关键词规则抽取，匹配分由技能-JD 关键词重叠驱动（命中≥3 首轮达标 / 2 次达标 / ≤1 降级）。
- `RUN_MODE=real`：组件真实 LLM / 搜索后端（仅需 `.env` 或控制台的 `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL`）；**组件异常时节点内确定性降级**（骨架简历 / 规则匹配 / 预置材料），不阻塞流程。
- 人工确认点：N2 画像缺失追问、N9 简历定稿确认（确认/修改/拒绝）均用 `interrupt()` + Checkpointer 实现（见设计文档 §2 N2/N9）；`config.skip_confirm=true` 可跳过 N9
