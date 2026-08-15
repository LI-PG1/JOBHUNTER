# 简历生成助手独立 EXE 版：安装指南与常见问题

简历生成助手 EXE 为**自包含单文件**分发：Python 运行时、全部依赖、前端界面均已打包进一个 `.exe`，**无需安装 Python、无需配置环境**，双击即用。

## 一、安装指南

### 1. 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11（64 位；Win7/8 未验证，不保证） |
| 磁盘空间 | ≥ 100MB（EXE 26.7MB + 数据目录） |
| 网络 | 首次使用需联网访问 LLM API（默认 DeepSeek） |
| 权限 | 普通用户权限即可，无需管理员 |

### 2. 安装步骤

1. 从 GitHub Releases 下载 `JL-Agent.exe`（**不要从源码仓库目录运行**，它是完整独立程序）。
2. 双击运行，或在任意目录双击 `JL-Agent.exe`。
3. 程序自动启动本地服务并**打开浏览器进入工作台**；控制台窗口显示运行日志（关闭窗口即退出服务）。

> 可选：将 EXE 放入固定文件夹（如 `D:\Apps\JL-Agent\`），并创建桌面快捷方式。

### 3. 首次使用（3 步）

1. **填简历**：基本信息、教育、实习、技能、荣誉、岗位 JD、项目经历。
2. **点生成**：选一页/两页与水印选项 → 实时进度生成。
3. **预览确认**：右侧预览 → 编辑 → 导出打印。

> LLM 密钥：点右上「⚙ 高级设置」→ 在 API Key 处粘贴 `sk-...`（也可放 `%LOCALAPPDATA%\JL-Agent\.env`）。

## 二、数据与配置位置

EXE 版数据统一存放在用户目录，卸载/替换 EXE **不会丢失**简历：

| 路径 | 内容 |
|---|---|
| `%LOCALAPPDATA%\JL-Agent\resumes` | 简历 JSON |
| `%LOCALAPPDATA%\JL-Agent\tasks` | 生成任务记录 |
| `%LOCALAPPDATA%\JL-Agent\photos` | 证件照 |
| `%LOCALAPPDATA%\JL-Agent\cache` | JD 分析缓存 |
| `%LOCALAPPDATA%\JL-Agent\.env` | 手动配置的 API Key（可选） |

## 三、常见问题（FAQ）

| # | 问题 | 处理 |
|---|---|---|
| 1 | 双击无反应 / 杀毒误报 | 首次运行 Windows SmartScreen 提示"已保护你的电脑"→ 点「更多信息」→「仍要运行」；将 EXE 加入信任列表 |
| 2 | 浏览器未自动打开 | 手动访问控制台窗口显示的地址（通常 `http://127.0.0.1:8000`） |
| 3 | 提示端口被占用 | EXE 自动顺延端口（8000→8001→…）；仍失败请关闭占用程序 |
| 4 | 生成报"LLM 调用失败" | 检查高级设置中 API Key 是否正确、网络是否可访问 LLM 服务 |
| 5 | 卡在"配置中…"/无法联网搜索 | 检查网络；Tavily Key 见高级设置内教程 |
| 6 | 数据会丢吗？ | 不会。简历存于 `%LOCALAPPDATA%\JL-Agent`，更新 EXE 前可整体备份该目录 |
| 7 | 如何升级新版本？ | 下载新 EXE 覆盖旧文件即可；数据自动沿用 |
| 8 | 更换电脑迁移数据 | 拷贝 `%LOCALAPPDATA%\JL-Agent` 目录到新电脑同路径 |
| 9 | 关闭后服务还在吗？ | 关闭控制台窗口即退出；若窗口已关但端口仍占用，任务管理器结束 `JL-Agent.exe` |
| 10 | 需要管理员权限吗？ | 不需要 |

## 四、重建 EXE（创作者侧）

```powershell
.venv\Scripts\python.exe portable\build_exe.py
# 产物：dist\JL-Agent.exe
```

- 打包入口：`portable\exe_entry.py`（自动选端口、开浏览器、数据重定向）。
- 构建要求：Windows + Python 3.12 + 已装依赖（PyInstaller 自动处理）。
- 发布：上传到 GitHub Releases（打 tag `v<版本>` 触发 CI 可全自动）。
