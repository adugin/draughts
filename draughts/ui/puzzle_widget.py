"""Puzzle Trainer dialog (D13) — solve tactical positions.

User clicks to make a move on a locked position board.
Correct move → green flash + auto-advance.
Wrong move   → red flash + reset (max 3 attempts, then reveal solution).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from draughts.config import EMPTY, Color
from draughts.game.board import Board
from draughts.game.puzzles import Puzzle, PuzzleSet, load_bundled_puzzles
from draughts.ui.board_widget import BoardWidget

logger = logging.getLogger("draughts.puzzle_trainer")

# Progress file lives in ~/.draughts/puzzle_progress.json
_PROGRESS_PATH = Path.home() / ".draughts" / "puzzle_progress.json"

# Theme colors are loaded dynamically from the theme engine
from draughts.ui.theme_engine import get_theme_colors as _get_theme_colors

# ---------------------------------------------------------------------------
# Session progress helpers
# ---------------------------------------------------------------------------


def _load_progress() -> dict:
    """Load progress from disk, returning defaults if file doesn't exist."""
    defaults: dict = {
        "solved": [],
        "streak": 0,
        "best_streak": 0,
        "total_attempts": 0,
        "total_correct": 0,
    }
    if _PROGRESS_PATH.exists():
        try:
            data = json.loads(_PROGRESS_PATH.read_text(encoding="utf-8"))
            for key, val in defaults.items():
                data.setdefault(key, val)
            return data
        except Exception:
            logger.warning("Failed to load puzzle progress, using defaults")
    return defaults


def _save_progress(progress: dict) -> None:
    """Persist progress to disk."""
    try:
        _PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("Failed to save puzzle progress")


# ---------------------------------------------------------------------------
# Move parsing helper
# ---------------------------------------------------------------------------


def _notation_to_path(move_str: str) -> list[tuple[int, int]]:
    """Convert 'c3:e5:g3' or 'c3-e5' to a list of (x, y) board positions."""
    sep = ":" if ":" in move_str else "-"
    return [Board.notation_to_pos(sq) for sq in move_str.split(sep)]


def _path_to_notation(path: list[tuple[int, int]]) -> str:
    """Convert a list of (x, y) positions to algebraic notation string."""
    sep = ":" if len(path) > 2 else ("-" if len(path) == 2 else ":")
    # Determine separator from whether it's a capture (landing != adjacent)
    parts = [Board.pos_to_notation(x, y) for x, y in path]
    return sep.join(parts)


def _captured_squares(path: list[tuple[int, int]]) -> set[tuple[int, int]]:
    """Return the set of squares that a capture path jumps over.

    In Russian draughts a flying king can land several squares past the
    captured piece, so the captured piece is NOT a member of ``path`` —
    it sits on the diagonal between consecutive path elements.  For
    ordinary pawns (jump distance 2) there is exactly one square between
    consecutive elements.

    Two capture paths that jump over the *same* set of opponent pieces
    are strategically equivalent (the only difference is where the
    capturing piece lands after the final jump).
    """
    result: set[tuple[int, int]] = set()
    for i in range(len(path) - 1):
        x1, y1 = path[i]
        x2, y2 = path[i + 1]
        dx = 1 if x2 > x1 else -1
        dy = 1 if y2 > y1 else -1
        cx, cy = x1 + dx, y1 + dy
        while (cx, cy) != (x2, y2):
            result.add((cx, cy))
            cx += dx
            cy += dy
    return result


def _captured_squares_on_board(path: list[tuple[int, int]], board: Board) -> set[tuple[int, int]]:
    """Return the set of squares actually occupied by opponent pieces that a
    capture path jumps over.

    Unlike ``_captured_squares`` this version consults the board so that
    empty intermediate squares (possible for flying-king long diagonal paths)
    are excluded.  Only squares where ``board.piece_at`` returns non-zero are
    included, giving the true set of captured pieces rather than every square
    traversed.
    """
    result: set[tuple[int, int]] = set()
    for i in range(len(path) - 1):
        x1, y1 = path[i]
        x2, y2 = path[i + 1]
        dx = 1 if x2 > x1 else -1
        dy = 1 if y2 > y1 else -1
        cx, cy = x1 + dx, y1 + dy
        while (cx, cy) != (x2, y2):
            if board.piece_at(cx, cy) != 0:
                result.add((cx, cy))
            cx += dx
            cy += dy
    return result


def _get_all_legal_paths(board: Board, turn: Color) -> list[list[tuple[int, int]]]:
    """Return all legal move paths for the given side.

    Returns captures if any exist, otherwise simple moves (mandatory capture rule).
    Each path is a list of (x, y) positions including the start square.
    """
    positions = np.argwhere(board.grid > 0) if turn == Color.BLACK else np.argwhere(board.grid < 0)
    captures = []
    simple = []
    for pos in positions:
        y, x = int(pos[0]), int(pos[1])
        caps = board.get_captures(x, y)
        if caps:
            captures.extend(caps)
        else:
            for tx, ty in board.get_valid_moves(x, y):
                simple.append([(x, y), (tx, ty)])
    return captures if captures else simple


# ---------------------------------------------------------------------------
# Puzzle Trainer dialog
# ---------------------------------------------------------------------------


class PuzzleTrainer(QDialog):
    """Puzzle trainer — user finds the best move on a given position."""

    MAX_ATTEMPTS = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Тренировка — Решать задачи")
        self.setMinimumSize(560, 660)
        self.resize(660, 740)

        # Resolve theme colors once for this dialog
        self._tc = _get_theme_colors("dark_wood")
        from draughts.ui.theme_engine import apply_theme as _apply_engine_theme

        _apply_engine_theme(self, "dark_wood")

        # Load puzzles and progress
        self._puzzles: PuzzleSet = load_bundled_puzzles()
        self._progress: dict = _load_progress()

        # Current puzzle state
        self._current_puzzle: Puzzle | None = None
        self._current_board: Board | None = None
        self._attempts: int = 0
        self._selected_sq: tuple[int, int] | None = None  # piece selected by user
        self._capture_in_progress: list[tuple[int, int]] = []  # partial capture path
        self._difficulty_filter: int | None = None  # None = all
        self._hint_shown: bool = False
        self._solved_this_puzzle: bool = False
        self._puzzle_index: int = 0  # index in current filtered list

        self._build_ui()
        self._load_next_puzzle(direction=0)  # load first puzzle

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        tc = self._tc
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Top bar: title + difficulty filter
        top = QHBoxLayout()
        title_lbl = QLabel("Решать задачи")
        title_lbl.setStyleSheet(f"color: {tc['fg']}; font-size: 16px; font-weight: bold;")
        top.addWidget(title_lbl)
        top.addStretch()

        diff_lbl = QLabel("Уровень:")
        diff_lbl.setStyleSheet(f"color: {tc['fg_muted']}; font-size: 13px;")
        top.addWidget(diff_lbl)

        self._diff_combo = QComboBox()
        self._diff_combo.addItem("Все уровни", None)
        self._diff_combo.addItem("★☆☆☆ Начинающий", 1)
        self._diff_combo.addItem("★★☆☆ Средний", 2)
        self._diff_combo.addItem("★★★☆ Сложный", 3)
        self._diff_combo.addItem("★★★★ Мастер", 4)
        self._diff_combo.currentIndexChanged.connect(self._on_difficulty_changed)
        top.addWidget(self._diff_combo)

        root.addLayout(top)

        # Puzzle meta bar: id, category, difficulty, turn
        self._meta_lbl = QLabel()
        self._meta_lbl.setStyleSheet(f"color: {tc['fg_muted']}; font-size: 12px;")
        root.addWidget(self._meta_lbl)

        # Description label
        self._desc_lbl = QLabel()
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet(f"color: {tc['fg']}; font-size: 13px; padding: 4px 0;")
        root.addWidget(self._desc_lbl)

        # Status label (feedback to user)
        self._status_lbl = QLabel(" ")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {tc['fg']}; padding: 4px;")
        root.addWidget(self._status_lbl)

        # Board widget
        self._board_widget = BoardWidget()
        self._board_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._board_widget.cell_left_clicked.connect(self._on_cell_click)
        root.addWidget(self._board_widget)

        # Buttons row (styled by the app-level QSS from theme engine)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_hint = QPushButton("Подсказка")
        self._btn_hint.clicked.connect(self._on_hint)
        btn_row.addWidget(self._btn_hint)

        self._btn_show = QPushButton("Показать ответ")
        self._btn_show.setVisible(False)
        self._btn_show.clicked.connect(self._on_show_answer)
        btn_row.addWidget(self._btn_show)

        btn_row.addStretch()

        self._btn_prev = QPushButton("← Предыдущая")
        self._btn_prev.clicked.connect(lambda: self._load_next_puzzle(direction=-1))
        btn_row.addWidget(self._btn_prev)

        self._btn_next = QPushButton("Следующая →")
        self._btn_next.clicked.connect(lambda: self._load_next_puzzle(direction=1))
        btn_row.addWidget(self._btn_next)

        root.addLayout(btn_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {tc['fg_muted']};")
        root.addWidget(sep)

        # Stats footer
        self._stats_lbl = QLabel()
        self._stats_lbl.setStyleSheet(f"color: {tc['fg_muted']}; font-size: 12px;")
        self._stats_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._stats_lbl)

        self._update_stats_label()

    # ------------------------------------------------------------------
    # Puzzle loading
    # ------------------------------------------------------------------

    def _current_pool(self) -> list[Puzzle]:
        """Return the list of puzzles matching the current difficulty filter."""
        if self._difficulty_filter is None:
            return self._puzzles.all()
        return self._puzzles.get_by_difficulty(self._difficulty_filter)

    def _load_next_puzzle(self, direction: int = 1) -> None:
        """Advance to next/previous puzzle in the filtered list.

        direction=1 → next, direction=-1 → previous, direction=0 → first
        """
        pool = self._current_pool()
        if not pool:
            self._status_lbl.setText("Нет задач с этим уровнем сложности")
            return

        if direction == 0:
            self._puzzle_index = 0
        else:
            new_index = self._puzzle_index + direction
            if new_index >= len(pool):
                # Completed all puzzles — show summary
                self._show_completion_summary(pool)
                return
            elif new_index < 0:
                new_index = len(pool) - 1
            self._puzzle_index = new_index

        puzzle = pool[self._puzzle_index]
        self._load_puzzle(puzzle)

    def _show_completion_summary(self, pool: list) -> None:
        """Show a congratulatory dialog when all puzzles are completed."""
        from PyQt6.QtWidgets import QMessageBox

        total = len(pool)
        solved = sum(1 for p in pool if p.id in self._progress["solved"])
        correct = self._progress["total_correct"]
        attempts = self._progress["total_attempts"]
        accuracy = (correct / attempts * 100) if attempts > 0 else 0
        best_streak = self._progress["best_streak"]

        msg = QMessageBox(self)
        msg.setWindowTitle("Тренировка завершена!")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            f"🏆 Все {total} задач пройдены!\n\n"
            f"Решено: {solved}/{total}\n"
            f"Точность: {correct}/{attempts} ({accuracy:.0f}%)\n"
            f"Лучшая серия: {best_streak}\n\n"
            f"Начать сначала?"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.button(QMessageBox.StandardButton.Yes).setText("Заново")
        msg.button(QMessageBox.StandardButton.No).setText("Закрыть")

        result = msg.exec()
        if result == QMessageBox.StandardButton.Yes:
            self._puzzle_index = 0
            self._load_puzzle(pool[0])
        else:
            self.close()

    def _load_puzzle(self, puzzle: Puzzle) -> None:
        """Load a puzzle onto the board and reset state."""
        self._current_puzzle = puzzle
        self._attempts = 0
        self._hint_shown = False
        self._solved_this_puzzle = False
        self._selected_sq = None
        self._capture_in_progress = []

        # Build board from position string
        board = Board(empty=True)
        board.load_from_position_string(puzzle.position)
        self._current_board = board

        # Update widget
        self._board_widget.set_board(board)
        self._board_widget.set_selection()
        self._board_widget.set_destination()
        self._board_widget.set_capture_highlights([])

        # Determine turn label
        turn_label = "Белые ходят" if puzzle.turn == Color.WHITE else "Чёрные ходят"

        # Meta line
        pool = self._current_pool()
        idx_display = self._puzzle_index + 1
        total = len(pool)
        self._meta_lbl.setText(
            f"Задача {idx_display}/{total}  •  {puzzle.id}  •  "
            f"{puzzle.category_display}  •  {puzzle.difficulty_stars}  •  {turn_label}"
        )

        self._desc_lbl.setText(puzzle.description)
        self._status_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {self._tc['fg']}; padding: 4px;")
        self._status_lbl.setText("Найдите лучший ход")

        self._btn_hint.setEnabled(True)
        self._btn_hint.setText("Подсказка")
        self._btn_show.setVisible(False)

    # ------------------------------------------------------------------
    # Click handling (move input)
    # ------------------------------------------------------------------

    def _on_cell_click(self, x: int, y: int) -> None:
        """Handle a board cell click for move input."""
        if self._current_puzzle is None or self._current_board is None:
            return
        if self._solved_this_puzzle:
            return

        board = self._current_board
        turn = self._current_puzzle.turn

        # Are we mid-capture?
        if self._capture_in_progress:
            self._handle_capture_continuation(x, y)
            return

        # Check if clicked square has a piece of the correct color
        piece = board.piece_at(x, y)
        if piece == EMPTY:
            # Clicked empty square — maybe it's a move destination
            if self._selected_sq is not None:
                self._attempt_move(self._selected_sq, (x, y))
            return

        is_correct_color = (turn == Color.WHITE and Board.is_white(piece)) or (
            turn == Color.BLACK and Board.is_black(piece)
        )

        if not is_correct_color:
            # Clicked opponent's piece — deselect
            self._selected_sq = None
            self._board_widget.set_selection()
            self._board_widget.set_destination()
            return

        # Select the piece
        self._selected_sq = (x, y)
        self._board_widget.set_selection(x, y)

    def _handle_capture_continuation(self, x: int, y: int) -> None:
        """Handle click during a multi-capture sequence."""
        path_so_far = self._capture_in_progress
        board = self._current_board

        # Find captures available from the current end of the path
        cur_x, cur_y = path_so_far[-1]
        captures = board.get_captures(cur_x, cur_y)

        # Filter captures that start from the current position
        # (all get_captures paths start from the original piece position,
        #  but we need continuations from cur position)
        # We'll check if clicked square is a valid next step
        for _cap_path in captures:
            # cap_path includes the starting square as first element
            # Since we're mid-capture, we need the full-path approach differently.
            # We track the partial path ourselves.
            pass

        # Simpler approach: rebuild from partial path
        # Find all legal full paths that start with our partial path
        full_paths = _get_all_legal_paths(board, self._current_puzzle.turn)

        # Filter paths that start with the captured path so far, and whose
        # next step is (x, y)
        partial = path_so_far
        matching = [
            fp
            for fp in full_paths
            if fp[: len(partial)] == partial and len(fp) > len(partial) and fp[len(partial)] == (x, y)
        ]

        if not matching:
            # Invalid click during capture — cancel
            self._capture_in_progress = []
            self._selected_sq = None
            self._board_widget.set_selection()
            self._board_widget.set_destination()
            self._board_widget.set_capture_highlights([])
            return

        # Extend partial path
        extended = [*partial, (x, y)]

        # Check if any full legal path matches exactly
        exact = [fp for fp in full_paths if fp == extended]
        still_going = [fp for fp in full_paths if fp[: len(extended)] == extended and len(fp) > len(extended)]

        if exact and not still_going:
            # Completed capture — intermediates stay magenta, final
            # landing square gets green selection (same as start).
            self._board_widget.set_capture_highlights(list(extended[1:-1]))
            self._board_widget.set_destination(*extended[-1])
            self._capture_in_progress = []
            self._validate_move_path(extended)
        elif still_going:
            # Continue capture
            self._capture_in_progress = extended
            self._board_widget.set_capture_highlights(list(extended[1:]))
        else:
            # No valid continuation
            self._capture_in_progress = []
            self._selected_sq = None
            self._board_widget.set_selection()
            self._board_widget.set_destination()
            self._board_widget.set_capture_highlights([])

    def _attempt_move(self, from_sq: tuple[int, int], to_sq: tuple[int, int]) -> None:
        """Try a simple (non-capture) move from from_sq to to_sq."""
        board = self._current_board
        turn = self._current_puzzle.turn

        # Check if captures are mandatory
        if board.has_any_capture(turn):
            # Maybe this is the start of a capture
            captures = board.get_captures(*from_sq)
            # Check if to_sq is a valid one-step capture destination
            for cap_path in captures:
                if len(cap_path) >= 2 and cap_path[0] == from_sq and cap_path[1] == to_sq:
                    # Start of capture path
                    partial = [from_sq, to_sq]
                    full_paths = _get_all_legal_paths(board, turn)
                    still_going = [fp for fp in full_paths if fp[: len(partial)] == partial and len(fp) > len(partial)]
                    exact = [fp for fp in full_paths if fp == partial]
                    if still_going:
                        self._capture_in_progress = partial
                        self._board_widget.set_capture_highlights([to_sq])
                        return
                    elif exact:
                        self._board_widget.set_destination(*to_sq)
                        self._validate_move_path(partial)
                        return
            # Wrong: must capture but tried a simple move
            self._flash_wrong("Взятие обязательно!")
            self._selected_sq = None
            self._board_widget.set_selection()
            self._board_widget.set_destination()
            return

        # Check if the simple move is legal
        legal_moves = board.get_valid_moves(*from_sq)
        if to_sq not in legal_moves:
            self._selected_sq = None
            self._board_widget.set_selection()
            self._board_widget.set_destination()
            return

        # It's a legal simple move — highlight destination green, then validate
        self._board_widget.set_destination(*to_sq)
        path = [from_sq, to_sq]
        self._validate_move_path(path)

    # ------------------------------------------------------------------
    # Move validation
    # ------------------------------------------------------------------

    def _validate_move_path(self, path: list[tuple[int, int]]) -> None:
        """Check whether the user's move path matches the best_move.

        In Russian draughts a flying king can land on ANY empty square
        past the captured piece.  Two capture paths that jump over the
        same set of opponent pieces are strategically equivalent — only
        the final landing square differs.  So we accept any legal capture
        that removes the same pieces as the puzzle's best_move, not just
        an exact path match.
        """
        puzzle = self._current_puzzle
        best_path = _notation_to_path(puzzle.best_move)

        # Exact match — always correct
        if path == best_path:
            self._on_correct()
            return

        # Equivalent capture — the user's capture jumps over the same
        # opponent pieces as the best_move, but the flying king landed
        # on a different (equally valid) square.  Two cases:
        #
        # 1) Multi-capture (len >= 3): intermediate squares match,
        #    only the final landing differs.  E.g. a1:c3:e5:g7 vs
        #    a1:c3:e5:h8.
        #
        # 2) Single capture (len == 2): both paths start from the same
        #    square and jump over the same diagonal.  E.g. a1:c3 vs
        #    a1:d4 — both jump over b2.  We verify they lie on the
        #    same diagonal and the captured piece (the opponent piece
        #    between start and landing) is the same.
        if len(path) >= 3 and len(best_path) >= 3 and path[:-1] == best_path[:-1]:
            self._on_correct()
            return

        if len(path) == 2 and len(best_path) == 2 and path[0] == best_path[0]:
            # Both are single-segment moves from the same origin.  Accept as
            # equivalent only when they jump over exactly the same opponent
            # piece(s) on the board — not merely the same diagonal direction.
            # This correctly rejects captures of different pieces that happen
            # to share the same direction (BUG-005).
            user_caps = _captured_squares_on_board(path, self._current_board)
            best_caps = _captured_squares_on_board(best_path, self._current_board)
            if user_caps and user_caps == best_caps:
                self._on_correct()
                return

        # Check if it's even a legal move (could be wrong but legal)
        legal = _get_all_legal_paths(self._current_board, puzzle.turn)
        if path in legal:
            self._on_wrong_move()
        else:
            # Illegal — just deselect silently
            self._selected_sq = None
            self._board_widget.set_selection()
            self._board_widget.set_destination()
            self._capture_in_progress = []
            self._board_widget.set_capture_highlights([])

    # ------------------------------------------------------------------
    # Result handlers
    # ------------------------------------------------------------------

    def _on_correct(self) -> None:
        """User found the best move."""
        self._solved_this_puzzle = True
        puzzle = self._current_puzzle

        # Update progress
        if puzzle.id not in self._progress["solved"]:
            self._progress["solved"].append(puzzle.id)
        self._progress["total_attempts"] += 1
        self._progress["total_correct"] += 1

        first_attempt = self._attempts == 0
        if first_attempt and not self._hint_shown:
            self._progress["streak"] += 1
            if self._progress["streak"] > self._progress["best_streak"]:
                self._progress["best_streak"] = self._progress["streak"]
        else:
            self._progress["streak"] = 0

        self._update_stats_label()

        # Flash green — keep selection + capture highlights visible so the
        # user sees the full move chain (start = green, intermediates =
        # magenta, final landing = magenta) during the success flash.
        # They get cleared when the next puzzle loads.
        self._flash_status("✓ Правильно!", self._tc["green"])

        # Auto-advance after 1.5 s (highlights cleared by _load_puzzle)
        QTimer.singleShot(1500, lambda: self._load_next_puzzle(direction=1))

    def _on_wrong_move(self) -> None:
        """User made a legal but wrong move."""
        self._attempts += 1
        self._progress["total_attempts"] += 1
        self._progress["streak"] = 0

        self._selected_sq = None
        self._capture_in_progress = []
        self._board_widget.set_selection()
        self._board_widget.set_destination()
        self._board_widget.set_capture_highlights([])

        if self._attempts >= self.MAX_ATTEMPTS:
            self._flash_wrong(f"Попробуйте ещё раз ({self._attempts}/{self.MAX_ATTEMPTS})")
            self._btn_show.setVisible(True)
            self._btn_hint.setEnabled(False)
        else:
            self._flash_wrong(f"Попробуйте ещё раз ({self._attempts}/{self.MAX_ATTEMPTS})")

        self._update_stats_label()

    def _flash_wrong(self, text: str) -> None:
        """Show a red error message, then restore the neutral prompt."""
        self._status_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {self._tc['red']}; padding: 4px;")
        self._status_lbl.setText(text)
        QTimer.singleShot(2000, self._restore_status)

    def _flash_status(self, text: str, color: str) -> None:
        """Show a colored status message."""
        self._status_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {color}; padding: 4px;")
        self._status_lbl.setText(text)

    def _restore_status(self) -> None:
        """Restore the neutral 'find the best move' prompt."""
        if not self._solved_this_puzzle:
            self._status_lbl.setStyleSheet(
                f"font-size: 15px; font-weight: bold; color: {self._tc['fg']}; padding: 4px;"
            )
            self._status_lbl.setText("Найдите лучший ход")

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_hint(self) -> None:
        """Highlight the starting square of the correct move."""
        if self._current_puzzle is None:
            return
        self._hint_shown = True
        self._progress["streak"] = 0
        best_path = _notation_to_path(self._current_puzzle.best_move)
        if best_path:
            sx, sy = best_path[0]
            self._board_widget.start_hint_pulse([(sx, sy)])
        self._btn_hint.setEnabled(False)
        self._btn_hint.setText("Подсказка (показана)")

    def _on_show_answer(self) -> None:
        """Reveal the solution move on the board."""
        if self._current_puzzle is None:
            return
        self._solved_this_puzzle = True
        self._btn_show.setVisible(False)
        best_path = _notation_to_path(self._current_puzzle.best_move)
        # Highlight all squares in the solution path
        if best_path:
            sx, sy = best_path[0]
            self._board_widget.set_selection(sx, sy)
            self._board_widget.set_capture_highlights(best_path[1:])
        self._flash_status(f"Ответ: {self._current_puzzle.best_move}", self._tc["blue"])

    def _on_difficulty_changed(self, idx: int) -> None:
        """Filter changed — reload from the beginning of the filtered list."""
        self._difficulty_filter = self._diff_combo.currentData()
        self._puzzle_index = 0
        self._load_next_puzzle(direction=0)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _update_stats_label(self) -> None:
        p = self._progress
        solved = len(p["solved"])
        total = len(self._puzzles)
        streak = p["streak"]
        best = p["best_streak"]
        attempts = p["total_attempts"]
        correct = p["total_correct"]
        pct = int(correct / attempts * 100) if attempts > 0 else 0
        self._stats_lbl.setText(
            f"Решено: {solved}/{total}  •  Серия: {streak} (рекорд: {best})"
            f"  •  Попыток: {attempts}, правильных: {correct} ({pct}%)"
        )

    # ------------------------------------------------------------------
    # Dialog close
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        _save_progress(self._progress)
        super().closeEvent(event)

    def accept(self) -> None:
        _save_progress(self._progress)
        super().accept()

    def reject(self) -> None:
        _save_progress(self._progress)
        super().reject()
