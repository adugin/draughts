"""PostToolUse hook: auto-run ruff format + ruff check --fix on edited .py files."""
import json
import os
import subprocess
import sys

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")
normalized = file_path.replace(os.sep, "/")

if file_path.endswith(".py") and ("/draughts/" in normalized or "/tests/" in normalized):
    subprocess.run(["ruff", "format", file_path], capture_output=True)
    subprocess.run(["ruff", "check", "--fix", file_path], capture_output=True)
