"""简历生成助手版本更新检查器（仓库版/便携版通用）。

对比本地版本（app/version.py）与 GitHub Release 最新 tag（v<version>），
提示是否有可用更新。仅做检测与提示，不自动修改文件。

用法：
    python scripts\\update_check.py            # 检测并输出提示
    python scripts\\update_check.py --json    # JSON 输出（供脚本集成）

退出码：0=已是最新 / 2=有可用更新 / 1=检查失败（离线等）
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.version import UPDATE_API, __version__  # noqa: E402


def _parse_tag(tag: str):
    """'v0.6.0' → (0, 6, 0)；解析失败返回 None。"""
    v = tag.lstrip("vV")
    parts = []
    for seg in v.split(".")[:3]:
        try:
            parts.append(int(seg))
        except ValueError:
            return None
    return tuple(parts)


def fetch_latest():
    req = urllib.request.Request(UPDATE_API, headers={"User-Agent": "JL-Agent-update-check"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = data.get("tag_name", "")
    return tag, data.get("html_url", "")


def main():
    ap = argparse.ArgumentParser(description="简历生成助手版本更新检查")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    result = {
        "local": __version__,
        "latest": None,
        "update_available": False,
        "release_url": "",
    }
    try:
        tag, url = fetch_latest()
        result["latest"] = tag.lstrip("vV") or tag
        result["release_url"] = url
        remote = _parse_tag(tag)
        local = _parse_tag(__version__)
        if remote and local and remote > local:
            result["update_available"] = True
    except Exception as e:
        result["error"] = str(e)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print("[update] 检查失败（可能离线）：%s" % e)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["update_available"]:
            print("[update] 发现新版本 v%s → v%s：%s"
                  % (result["local"], result["latest"], result["release_url"]))
            print("        更新方式（仓库版）：git pull && pip install -r requirements.txt")
        else:
            print("[update] 已是最新版本 v%s" % result["local"])
    return 2 if result["update_available"] else 0


if __name__ == "__main__":
    sys.exit(main())
