"""CLI / MCP 工具：大脑的"手"——插件 = 可配置的命令工具（预置库 + 自定义）。

- mock 模式：只注册与返回工具元数据，**不真实执行命令**（安全护栏，避免误操作）
- real 模式：subprocess 执行 CLI 命令 / npx 启动 MCP server（预留，待接入 graph）
"""
import subprocess
from typing import Any, Dict

from tools.base import BaseTool, ToolResult

# 预置工具库：成熟、轻量，适配 Windows + 求职 Agent 场景
# install/uninstall：一键配置 / 一键卸载 时执行的依赖安装命令
PRESET_TOOLS = [
    {
        "id": "markitdown", "name": "MarkItDown（文档→Markdown）", "type": "cli",
        "command": "markitdown {input} -o {output}",
        "desc": "微软开源：PDF/DOCX/PPTX/XLSX/HTML 一键转 Markdown，用于解析简历 / JD / 面经文档",
        "install": "pip install markitdown",
        "uninstall": "pip uninstall -y markitdown",
    },
    {
        "id": "pypdf", "name": "pypdf（PDF 文本提取）", "type": "cli",
        "command": "python -c \"from pypdf import PdfReader; print('\\n'.join(p.extract_text() or '' for p in PdfReader(r'{input}').pages))\"",
        "desc": "纯 Python PDF 文本提取，轻量零依赖",
        "install": "pip install pypdf",
        "uninstall": "pip uninstall -y pypdf",
    },
    {
        "id": "playwright-mcp", "name": "Playwright MCP（浏览器自动化）", "type": "mcp",
        "command": "npx @playwright/mcp@latest",
        "desc": "微软官方：浏览器访问 / 抓取网页 / 模拟点击，用于查岗位详情与在线投递",
        "install": "npm install -g @playwright/mcp",
        "uninstall": "npm uninstall -g @playwright/mcp",
    },
    {
        "id": "fetch-mcp", "name": "Fetch MCP（网页抓取）", "type": "mcp",
        "command": "uvx mcp-server-fetch",
        "desc": "MCP 官方：URL 抓取并转 Markdown / 纯文本",
        "install": "pip install mcp-server-fetch",
        "uninstall": "pip uninstall -y mcp-server-fetch",
    },
    {
        "id": "filesystem-mcp", "name": "Filesystem MCP（沙箱文件）", "type": "mcp",
        "command": "npx -y @modelcontextprotocol/server-filesystem",
        "desc": "MCP 官方：受保护目录内文件读写 / 搜索 / 复制",
        "install": "npm install -g @modelcontextprotocol/server-filesystem",
        "uninstall": "npm uninstall -g @modelcontextprotocol/server-filesystem",
    },
    {
        "id": "git-mcp", "name": "Git MCP（代码版本）", "type": "mcp",
        "command": "npx -y @modelcontextprotocol/server-git",
        "desc": "MCP 官方：git 仓库操作（status / diff / log / commit）",
        "install": "npm install -g @modelcontextprotocol/server-git",
        "uninstall": "npm uninstall -g @modelcontextprotocol/server-git",
    },
    {
        "id": "context7-mcp", "name": "Context7（技术文档）", "type": "mcp",
        "command": "npx -y @upstash/context7-mcp",
        "desc": "Upstash：查询最新版库文档，用于技术栈调研与补课",
        "install": "npm install -g @upstash/context7-mcp",
        "uninstall": "npm uninstall -g @upstash/context7-mcp",
    },
    {
        "id": "memory-mcp", "name": "Memory MCP（长期记忆）", "type": "mcp",
        "command": "npx -y @modelcontextprotocol/server-memory",
        "desc": "MCP 官方：知识图谱式记忆，跨会话记住用户偏好与投递上下文",
        "install": "npm install -g @modelcontextprotocol/server-memory",
        "uninstall": "npm uninstall -g @modelcontextprotocol/server-memory",
    },
    {
        "id": "time-mcp", "name": "Time MCP（时间 / 定时）", "type": "mcp",
        "command": "npx -y @modelcontextprotocol/server-time",
        "desc": "MCP 官方：时区 / 时间查询与定时提醒",
        "install": "npm install -g @modelcontextprotocol/server-time",
        "uninstall": "npm uninstall -g @modelcontextprotocol/server-time",
    },
]


class CliTool(BaseTool):
    """CLI 工具：mock 不真执行；real 走 subprocess。"""

    name = "cli"

    def _mock(self, payload: Dict[str, Any]) -> ToolResult:
        return ToolResult(ok=True, data={
            "mode": "mock（仅注册，不真实执行）",
            "tools": PRESET_TOOLS,
            "note": "在控制台启用工具后，real 模式将由 Agent 按配置执行 CLI / 启动 MCP server",
        })

    def _real(self, payload: Dict[str, Any]) -> ToolResult:
        cmd = str(payload.get("command") or "").strip()
        if not cmd:
            return ToolResult(ok=False, error="缺少 command")
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            return ToolResult(
                ok=proc.returncode == 0,
                data={"stdout": proc.stdout[-4000:], "stderr": proc.stderr[-2000:]},
                error=proc.stderr[-2000:] if proc.returncode else "",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, error="命令执行超时（120s）")
        except Exception as e:
            return ToolResult(ok=False, error=f"命令执行失败：{e}")
