"""简历生成助手版本号（单点维护）。

发布新版本时仅需修改 __version__；版本更新检查（scripts/update_check.py）
与 GitHub Release tag（v<__version__>）保持一致。
"""
__version__ = "0.6.1"
VERSION = __version__

# 版本更新检查源（GitHub Release latest tag，用于 update_check.py）
UPDATE_REPO = "LI-PG1/JL-Agent"
UPDATE_API = "https://api.github.com/repos/{repo}/releases/latest".format(repo=UPDATE_REPO)
