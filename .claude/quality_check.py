"""PreToolUse hook: block `git commit` unless code quality gates pass.

Industry-standard pre-commit gates (fast, ≤15s, BLOCKING):
  1. ruff check      — linter, zero warnings allowed
  2. ruff format --check — formatting, must be idempotent
  3. mypy (strict core modules) — type safety
  4. bandit HIGH severity — no critical security issues
  5. pytest -q       — full test suite must pass

Slow/noisy tools (vulture, radon, mypy on UI code) are NOT run here —
see `.claude/quality_full.py` for the advisory full audit intended
for manual runs or CI pipelines, not every commit.

Exit code contract (Claude Code hook protocol):
  0  → approve tool call
  2  → block tool call; stderr is shown to Claude
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _is_git_commit(command: str) -> bool:
    """True if the Bash command is a `git commit` (not push/log/etc)."""
    tokens = command.strip().split()
    if not tokens or tokens[0] != "git":
        return False
    # find first non-flag token after `git`
    for t in tokens[1:]:
        if not t.startswith("-"):
            return t == "commit"
    return False


def _run(cmd: list[str], cwd: Path = REPO) -> tuple[int, str]:
    """Run a command, return (exit_code, combined_output)."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=180, check=False
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return 127, f"Tool not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"Timeout: {' '.join(cmd)}"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # Malformed input — do not block, let the commit proceed.
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    command = tool_input.get("command", "") if tool_name == "Bash" else ""

    if tool_name != "Bash" or not _is_git_commit(command):
        return 0

    failures: list[tuple[str, str]] = []

    # 1. ruff check
    rc, out = _run(["ruff", "check", "draughts/", "tests/"])
    if rc != 0:
        failures.append(("ruff check", out.strip()))

    # 2. ruff format --check
    rc, out = _run(["ruff", "format", "--check", "draughts/", "tests/"])
    if rc != 0:
        failures.append(("ruff format --check", out.strip()))

    # 3. mypy (scoped to strict modules configured in pyproject.toml)
    rc, out = _run(["mypy", "draughts/game/", "draughts/engine/"])
    if rc != 0:
        # strip noise: only keep lines with "error:" or the summary
        lines = [ln for ln in out.splitlines() if "error:" in ln or "Found" in ln]
        failures.append(("mypy", "\n".join(lines) or out.strip()))

    # 4. bandit HIGH severity only
    rc, out = _run(
        ["bandit", "-r", "draughts/", "-q", "-ll", "-iii", "--format", "txt"]
    )
    # bandit exits 1 when issues are found. We only block on HIGH (-iii).
    if rc == 1:
        failures.append(("bandit HIGH", out.strip()))

    # 5. pytest
    rc, out = _run(["python", "-m", "pytest", "tests/", "-q", "--tb=short"])
    if rc != 0:
        tail = "\n".join(out.splitlines()[-40:])
        failures.append(("pytest", tail))

    if not failures:
        return 0

    # Report to Claude via stderr + exit 2
    print("Commit BLOCKED by quality gate. Fix issues below, then retry.", file=sys.stderr)
    for tool, detail in failures:
        print(f"\n--- {tool} ---", file=sys.stderr)
        print(detail, file=sys.stderr)
    print(
        "\nTo bypass (not recommended), the user can run:\n"
        "  git commit --no-verify  (does not apply here — this is a Claude hook).\n"
        "The correct path is to fix the findings above.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
