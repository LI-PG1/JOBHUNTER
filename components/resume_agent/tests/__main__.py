"""统一测试入口：python -m tests（在 resume_agent 目录下执行）。

自动发现并运行 tests/test_*.py 全部用例。
"""
import os
import sys
import unittest
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1]
TESTS = COMPONENT / "tests"
sys.path.insert(0, str(COMPONENT.parent))   # components/
sys.path.insert(0, str(TESTS))

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(str(TESTS), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
