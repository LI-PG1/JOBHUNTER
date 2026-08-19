# JobHunter —— 求职全流程 AI 助手

> 单仓库自包含：clone 即用，仅需配置自己的 LLM Key。
> 简历生成 · 岗位匹配 · 面试准备 · 面试跟踪 四大板块，一个本地服务搞定。

## 快速开始

```powershell
# 1. 克隆仓库
git clone https://github.com/LI-PG1/JOBHUNTER.git
cd JOBHUNTER

# 2. 安装依赖（首次）
python -m pip install -r job-hunter-orchestrator/requirements.txt
python -m pip install -r components/resume_agent/lib/requirements.txt
python -m pip install -r components/match_agent/requirements.txt
python -m pip install -r components/prep_agent/requirements.txt

# 3. 配置 LLM Key（复制模板后填写；也可启动后在「控制台 → API Key」界面配置，即时生效）
Copy-Item job-hunter-orchestrator/.env.example job-hunter-orchestrator/.env
#   编辑 .env：填入 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（推荐 deepseek-v4-flash）

# 4. 启动服务
cd job-hunter-orchestrator
python -m uvicorn web.app:app --host 127.0.0.1 --port 2026

# 5. 浏览器打开 http://127.0.0.1:2026
```

> 无 Key 也可体验：`.env` 中 `RUN_MODE=mock`，全流程本地模拟，开箱即用。

## 四大板块

| 板块 | 说明 |
|---|---|
| 📄 简历生成 | 填写画像 → 生成 ATS 专业简历 → 版本管理与 PDF 导出 |
| 🎯 岗位匹配 | 基于画像搜索岗位并给出匹配度与相关链接 |
| 🎤 面试准备 | 自动生成自我介绍/项目深挖/八股等 8 份面试材料 |
| 📋 面试跟踪 | 投递进度、面试节点与提醒（本地 JSON 存储） |

## 目录结构

```
JobHunter\
├── job-hunter-orchestrator\   # 大脑：LangGraph 调度器 + Web UI（FastAPI）
│   ├── graph\                 # 节点与 StateGraph 装配（N2 画像追问 / N9 简历确认 interrupt）
│   ├── web\                   # Web 服务（前端 + 控制台 API Key 管理）
│   ├── clients\llm.py         # 进程内 LLM（OpenAI 兼容直连）
│   ├── run_full_e2e.py        # 全链路测试（mock，11 场景全过）
│   ├── requirements.txt
│   └── .env.example           # 唯一配置模板（LLM Key + RUN_MODE）
├── components\                # 三组件 + 跟踪器（进程内能力来源）
│   ├── resume_agent\          # 简历生成（ATS 模板 / 骨架映射）
│   ├── match_agent\           # 岗位匹配（规则+LLM 双评分 / 相关链接）
│   ├── prep_agent\            # 面试材料（8 份材料并发生成 + 质量回炉）
│   └── tracker_agent\         # 面试跟踪（本地 JSON 存储）
├── projects\                  # 四个子项目工程副本（只读参考，源文件不动）
├── _设计文档\                  # 架构与设计文档
└── .github\workflows\ci.yml   # CI：e2e + 组件单测（mock 免 Key）
```

## 运行模式

- `RUN_MODE=mock`：组件 mock 后端 / 占位 LLM，本地全流程模拟，无需 Key。
- `RUN_MODE=real`：组件真实 LLM / 搜索后端，仅需 `.env` 或控制台的 `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL`；组件异常时节点内确定性降级（骨架简历 / 规则匹配 / 预置材料），不阻塞流程。
- 人工确认点：N2 画像缺失追问、N9 简历确认（确认使用 / 修改 / 拒绝）用 `interrupt()` + Checkpointer 实现；`config.skip_confirm=true` 可跳过 N9。

## 测试

```powershell
# 全链路 e2e（mock，无需 Key）
cd job-hunter-orchestrator
$env:RUN_MODE = "mock"
python run_full_e2e.py

# 组件单测
cd components/match_agent && python -m tests
cd ../resume_agent && python -m tests
```

CI（`.github/workflows/ci.yml`）在每次 push 时自动运行上述测试。

## License

[MIT](LICENSE)
