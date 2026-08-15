"""构建简历生成助手独立 EXE（PyInstaller onefile，自包含、免装 Python）。

用法：
    .venv\\Scripts\\python.exe portable\\build_exe.py

产物：dist\\JL-Agent.exe（单文件，双击即用，自动打开浏览器工作台）
说明：- app 包通过入口 import 自动收集；rules/templates/frontend/config 为数据文件
       - hidden-import 补齐 uvicorn 运行时动态导入；multipart 为 python-multipart 包名
       - 用户数据自动重定向到 %LOCALAPPDATA%\\JL-Agent（见 exe_entry.py）
"""
import subprocess
import sys
from pathlib import Path

# 强制 UTF-8 输出：Actions(en-US)/非 UTF-8 控制台下中文 print 会抛 UnicodeEncodeError 导致构建失败
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent

DATA_FILES = [
    ("rules", "rules"),
    ("templates", "templates"),
    ("frontend", "frontend"),
    ("config.example.json", "."),
]
HIDDEN_IMPORTS = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "multipart",
]


def build():
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--onefile", "--console", "--name", "JL-Agent"]
    for src, dst in DATA_FILES:
        cmd += ["--add-data", "%s;%s" % (src, dst)]
    for h in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", h]
    cmd.append(str(REPO / "portable" / "exe_entry.py"))
    print("[build-exe] " + " ".join(cmd[:20]) + " ...")
    subprocess.run(cmd, cwd=REPO, check=True)
    exe = REPO / "dist" / "JL-Agent.exe"
    if not exe.exists():
        raise SystemExit("构建失败：未找到 " + str(exe))
    print("[build-exe] 完成：" + str(exe) + "（%.1f MB）" % (exe.stat().st_size / 1e6))


if __name__ == "__main__":
    build()
