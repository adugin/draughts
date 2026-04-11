"""Tests for CLI argument parsing."""

import subprocess
import sys

import draughts
from main import _build_parser


class TestArgParser:
    """Test argument parsing without launching GUI."""

    def test_version(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--version"],
            capture_output=True,
            text=True,
        )
        assert draughts.__version__ in result.stdout
        assert result.returncode == 0

    def test_no_args(self):
        args = _build_parser().parse_args([])
        assert args.savefile is None
        assert args.resume is False
        assert args.difficulty is None
        assert args.depth is None
        assert args.black is False

    def test_savefile(self):
        args = _build_parser().parse_args(["game.json"])
        assert args.savefile == "game.json"

    def test_resume(self):
        args = _build_parser().parse_args(["--resume"])
        assert args.resume is True

    def test_difficulty(self):
        for d in (1, 2, 3):
            args = _build_parser().parse_args(["--difficulty", str(d)])
            assert args.difficulty == d

    def test_depth(self):
        args = _build_parser().parse_args(["--depth", "8"])
        assert args.depth == 8

    def test_black(self):
        args = _build_parser().parse_args(["--black"])
        assert args.black is True

    def test_combined(self):
        args = _build_parser().parse_args(["save.json", "--difficulty", "3", "--black", "--depth", "6"])
        assert args.savefile == "save.json"
        assert args.difficulty == 3
        assert args.black is True
        assert args.depth == 6

    def test_invalid_difficulty_rejected(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--difficulty", "5"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2

    def test_missing_file_rejected(self):
        result = subprocess.run(
            [sys.executable, "main.py", "no_such_file_12345.json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2

    def test_depth_out_of_range_rejected(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--depth", "99"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
