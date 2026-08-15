# 简历生成助手部署与维护指南

本指南覆盖：环境要求、安装配置、启动运维、版本更新机制与常见问题，适用于从源码（仓库版）部署简历生成助手的场景。

## 1. 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11、macOS、主流 Linux 发行版 |
| Python | **3.10 ~ 3.12**（3.12 推荐；不要求预装，便携版内置运行时） |
| 内存 | ≥ 2GB（LLM 请求本身在云端，本地仅推理编排） |
| 网络 | 需访问 LLM API（默认 DeepSeek，可改 base_url）；可选访问 GitHub（版本检查/插件安装） |
| 磁盘 | 源码 ~10MB；数据目录随简历数量增长（预计 <100MB/千份） |

> 无需预装 Python 的部署方式：便携版分发（ZIP 自包含 / EXE），见 [EXE_GUIDE.md](EXE_GUIDE.md)。

## 2. 安装（从源码）

```bash
git clone https://github.com/LI-PG1/JL-Agent.git
cd JL-Agent

# 创建虚拟环境（隔离依赖，避免污染系统 Python）
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 3. 环境配置

### 3.1 密钥（.env）

```bash
cp .env.example .env     # 编辑填入真实密钥
```

| 变量 | 说明 | 示例 |
|---|---|---|
| `DEEPSEEK_API_KEY` | LLM API Key（OpenAI 兼容） | `sk-xxxx` |
| `TAVILY_API_KEY` | 联网搜索 Key（可选，开启深度搜索时） | `tvly-xxxx` |

> `.env` 已被 .gitignore 排除，**不会入库**。密钥在 UI 中脱敏展示。

### 3.2 运行配置（config.json）

```bash
cp config.example.json config.json   # 可选；不创建则自动回退到 example
```

| 配置节 | 键 | 说明 | 默认 |
|---|---|---|---|
| `provider` | `base_url` | LLM 接口地址 | DeepSeek 官方 |
| `provider` | `model` | 模型名 | `deepseek-v4-flash` |
| `provider` | `api_key_env` | API Key 环境变量名 | `DEEPSEEK_API_KEY` |
| `search.api` | `provider` / `api_key_env` / `interval_seconds` | 搜索服务配置 | Tavily / 1.1s |
| `paths` | `data_dir` / `rules_dir` / `templates_dir` | 资源路径（相对项目根） | data / rules / templates |
| `limits` | 各字段数量上限 | 教育/实习/JD/照片大小约束 | 见 config.example.json |

### 3.3 数据与资源

| 路径 | 用途 | 是否入库 |
|---|---|---|
| `data/` | 简历 JSON、settings.json（含密钥/插件状态）、任务缓存 | 否（gitignore） |
| `rules/` | 行业/技能/JD/项目规则（jsonschema 校验后加载） | 是 |
| `templates/` | 一页/两页简历模板 | 是 |
| `frontend/` | 原生前端（零构建） | 是 |

## 4. 启动

### 开发/日常

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000>。健康检查：`GET /api/health`（返回规则版本与 **应用版本**）。

### 生产部署（可选加固）

- **反向代理 + HTTPS**：Nginx 反代 `127.0.0.1:8000`，WebSocket（SSE 进度）需配置 `proxy_buffering off`。
- **systemd（Linux）**：

```ini
[Unit]
Description=JL-Agent
After=network.target
[Service]
WorkingDirectory=/opt/JL-Agent
ExecStart=/opt/JL-Agent/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
[Install]
WantedBy=multi-user.target
```

## 5. 版本更新机制

### 5.1 版本号维护（单点）

- 应用版本唯一来源：[app/version.py](../app/version.py) 的 `__version__`。
- 发布新版本时：`__version__` 升级 → 打 Git tag `v<version>` → 推送到 GitHub（tag 触发 Release/CI 构建，见 5.3）。

### 5.2 更新检查（用户侧）

```bash
python scripts\update_check.py          # 提示是否可更新
python scripts\update_check.py --json   # 机器可读输出
```

- 对比本地 `__version__` 与 GitHub `releases/latest` 的 tag；
- 退出码：`0` 已最新 / `2` 可更新 / `1` 检查失败（离线等）。

### 5.3 发布流程（创作者侧）

```bash
# 1. 更新 app/version.py 版本号并提交
# 2. 打标签（触发 GitHub Actions 自动构建 Release 产物）
git tag v0.6.0 && git push origin v0.6.0
# 3. 人工复核 GitHub Releases 页（源码 zip 自动附带）
```

## 6. 测试

```bash
.venv\Scripts\python.exe tests\smoke_api.py      # API 冒烟（无需 LLM Key）
.venv\Scripts\python.exe tests\logic_check.py    # 核心逻辑回归（无 LLM 依赖）
```

## 7. 常见问题（FAQ）

| 问题 | 处理 |
|---|---|
| 8000 端口被占用 | 换端口启动：`uvicorn ... --port 8001` |
| 生成报错"LLM 调用失败" | 检查 .env 的 Key 与网络；确认 base_url 可达 |
| 规则版本报错/加载失败 | 更新后 `rules/` 与代码同步升级，重启服务 |
| 插件一键配置失败 | 见高级设置内 installMsg 的排查步骤（网络/权限/PATH） |
| 忘记 Key / 想换模型 | 改 .env 与 config.json，重启服务 |

## 8. 可扩展性说明

- **新增规则**：`rules/` 下按 schema 添加/修改 JSON，重启即生效（health 暴露版本号便于校验）。
- **新增 API**：在 `app/api/` 添加路由模块并注册到 `app/main.py`，前端为原生 JS（零构建）。
- **新增插件**：在 `app/api/settings.py` 的 `PLUGIN_REGISTRY` 按双层启动结构登记（runtime/features/defaultConfig/loginNotice）。
- **新增分发产物**：便携版（ZIP/EXE）由 `portable/` 下脚本构建，接入 CI 即可全自动。
