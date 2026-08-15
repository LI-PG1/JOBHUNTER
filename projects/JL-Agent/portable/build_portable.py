"""构建简历生成助手便携版分发 ZIP（自包含、免装 Python、开箱即用）。

用法：
    .venv\\Scripts\\python.exe portable\\build_portable.py [--out dist] [--skip-download]

流程：
  1) 下载官方嵌入式 Python {EMBED_VER}（win_amd64，约 11MB）→ dist/python
  2) 用本机 pip 收集全部运行依赖 → dist/python/Lib/site-packages（cp312 轮子，
     与嵌入式运行时 ABI 一致；复用本机缓存加速）
  3) 拷贝应用代码（app/rules/templates/frontend + 配置文件）与便携启动器
     （run.py / 启动JL-Agent.bat）→ dist/
  4) 写入 python312._pth：启用 site 并加载 Lib\\site-packages
  5) 压缩 → JL-Agent-portable.zip

产物目录（解压后即用）：
    JL-Agent-portable/
    ├── 启动JL-Agent.bat         双击启动（自动选择系统 Python / 内置嵌入式）
    ├── run.py
    ├── app/ rules/ templates/ frontend/
    └── python/                 嵌入式 Python 3.12 + 全部依赖
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# 强制 UTF-8 输出：Actions(en-US)/非 UTF-8 控制台下中文 print 会抛 UnicodeEncodeError 导致构建失败
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EMBED_VER = "3.12.10"
EMBED_URL = ("https://www.python.org/ftp/python/{ver}/python-{ver}-embed-amd64.zip"
             .format(ver=EMBED_VER))
REPO = Path(__file__).resolve().parent.parent          # JL-Agent 项目根
PORTABLE = Path(__file__).resolve().parent             # portable/ 目录
# 仓库内置缓存（离线优先）：Actions/无外网环境直接使用，避免 python.org 对数据中心 IP 拦截
EMBED_BUNDLED = PORTABLE / "embed" / ("python-%s-embed-amd64.zip" % EMBED_VER)
COPY_DIRS = ["app", "rules", "templates", "frontend"]
COPY_FILES = ["config.example.json", ".env.example", "README.md"]


def log(msg):
    print("[build] " + msg, flush=True)


def download(url, dest):
    if dest.exists() and dest.stat().st_size > 5_000_000:
        log("已存在，跳过下载：" + dest.name)
        return dest
    log("下载 " + url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "JL-Agent-build"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    log("下载完成：" + dest.name + "（%.1f MB）" % (dest.stat().st_size / 1e6))
    return dest


def build(out: Path, skip_download: bool):
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)

    # ---- 1) 嵌入式 Python ----
    # 优先使用仓库内置 zip（离线、不受外网影响）；否则下载并缓存到 _embed_cache
    embed_zip = EMBED_BUNDLED if EMBED_BUNDLED.exists() else (
        Path(temp_dir := out.parent / "_embed_cache") / ("python-%s-embed-amd64.zip" % EMBED_VER))
    if not EMBED_BUNDLED.exists():
        if skip_download:
            if not embed_zip.exists():
                log("--skip-download 但缓存不存在：" + str(embed_zip))
                sys.exit(1)
        else:
            download(EMBED_URL, embed_zip)
    log("解压嵌入式 Python → python/")
    with zipfile.ZipFile(embed_zip) as zf:
        zf.extractall(out / "python")
    _pth = next(out.joinpath("python").glob("python3*_pth"))
    log("改写 %s：启用 site + Lib\\site-packages" % _pth.name)
    # 标准库 zip 名为 python{主版本}{次版本}.zip（如 python312.zip）
    maj, minor = (int(x) for x in EMBED_VER.split(".")[:2])
    _pth.write_text(
        "python{maj}{min}.zip\n.\nLib\\site-packages\nimport site\n".format(
            maj=maj, min=minor),
        encoding="utf-8")

    # ---- 2) 依赖收集（与嵌入式 ABI 一致的 cp312 轮子）----
    site = out / "python" / "Lib" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    req = REPO / "requirements.txt"
    log("收集依赖 → python/Lib/site-packages（pip install --target）")
    subprocess.run([sys.executable, "-m", "pip", "install", "--target", str(site),
                    "-r", str(req), "--no-warn-script-location"],
                   check=True)
    # 清理 pip 生成的 bin/ 与缓存
    for p in site.parent.iterdir():
        if p.name in ("bin", "__pycache__"):
            shutil.rmtree(p, ignore_errors=True)

    # ---- 3) 应用代码 + 启动器 ----
    log("拷贝应用代码与启动器")
    for d in COPY_DIRS:
        shutil.copytree(REPO / d, out / d,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in COPY_FILES:
        if (REPO / f).exists():
            shutil.copy2(REPO / f, out / f)
    shutil.copy2(PORTABLE / "run.py", out / "run.py")
    shutil.copy2(PORTABLE / "启动JL-Agent.bat", out / "启动JL-Agent.bat")

    # ---- 4) 压缩 ----
    zip_path = out / "JL-Agent-portable.zip"
    if zip_path.exists():
        zip_path.unlink()
    log("压缩 → " + zip_path.name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(out):
            root_p = Path(root)
            for fn in files:
                full = root_p / fn
                arc = full.relative_to(out)
                zf.write(full, arcname=str(arc))
    size_mb = zip_path.stat().st_size / 1e6
    log("构建完成：" + str(zip_path) + "（%.1f MB）" % size_mb)
    log("用法：解压 JL-Agent-portable.zip 后双击 启动JL-Agent.bat")
    return zip_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="构建简历生成助手便携版 ZIP")
    ap.add_argument("--out", default=str(REPO / "dist"), help="输出目录（默认项目根 dist）")
    ap.add_argument("--skip-download", action="store_true",
                    help="复用已缓存的嵌入式 Python zip（默认自动下载）")
    args = ap.parse_args()
    build(Path(args.out), args.skip_download)
