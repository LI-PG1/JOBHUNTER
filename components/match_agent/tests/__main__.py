"""match_agent 组件主测试入口。

整合 tests/ 下全部 test_*.py 用例并运行（unittest 自动发现）。
用法（在 components/match_agent 目录下）：
    python -m tests
新增测试模块（如 test_decide.py）放入本目录即可自动纳入。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent / "tools"))
sys.path.insert(0, str(TESTS_DIR.parent / "nodes"))


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(TESTS_DIR), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
