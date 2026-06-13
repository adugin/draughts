"""Full advisory quality audit — manual / CI use, not per-commit.

Runs the slower / noisier tools that are unsuitable for pre-commit:
  - vulture   (dead code; high false-positive rate on Qt slots)
  - bandit    (all severity levels, not just HIGH)
  - radon cc  (cyclomatic complexity, rank D+ flagged)
  - radon mi  (maintainability index, rank B+ flagged)
  - mypy      (whole codebase, not just strict modules)

These are REPORTED, not blocking. Use before merges / releases.

Run:
  python .claude/quality_full.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, cwd=REPO, check=False)
        return proc.returncode
    except FileNotFoundError:
        print(f"  (tool not installed: {cmd[0]})")
        return 127


def main() -> int:
    section("ruff (strict)")
    run(["ruff", "check", "draughts/", "tests/"])
    run(["ruff", "format", "--check", "draughts/", "tests/"])

    section("mypy (whole project)")
    run(["mypy", "draughts/"])

    section("bandit (all severities)")
    run(["bandit", "-r", "draughts/", "-q"])

    section("vulture (dead code, min confidence 80)")
    # Whitelist Qt-slot-like names to reduce noise.
    run([
        "vulture",
        "draughts/",
        "--min-confidence", "80",
        "--ignore-names", "_on_*,paintEvent,closeEvent,keyPressEvent,mousePressEvent,mouseReleaseEvent,mouseMoveEvent,resizeEvent,showEvent,hideEvent",
    ])

    section("radon cc (cyclomatic complexity, rank D+)")
    run(["radon", "cc", "draughts/", "-nd", "-s"])

    section("radon mi (maintainability index, rank B+)")
    run(["radon", "mi", "draughts/", "-nb", "-s"])

    section("pytest")
    run(["python", "-m", "pytest", "tests/", "-q"])

    print("\nAdvisory audit complete. Address HIGH-severity findings before release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
