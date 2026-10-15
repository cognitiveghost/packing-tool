"""Run the tests under both coverage gates: Python app code and the page scripts.

    python scripts/coverage_check.py [pytest args]

Python: coverage.py over packing_tool/ and gui/, gate in .coveragerc.
Page scripts: tests/js_coverage.py, V8 coverage read from QtWebEngine, each of
gui/web/*.js and their total at JS_FAIL_UNDER percent or more.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS_FAIL_UNDER = "80"


def main(argv: list[str]) -> int:
    env = {**os.environ, "JS_COVERAGE": "1", "JS_COVERAGE_FAIL_UNDER": JS_FAIL_UNDER}
    tests = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "-m", "pytest", *argv], cwd=ROOT, env=env, check=False
    )
    report = subprocess.run([sys.executable, "-m", "coverage", "report"], cwd=ROOT, check=False)
    return tests.returncode or report.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
