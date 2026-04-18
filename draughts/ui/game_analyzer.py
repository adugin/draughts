"""Full-game analysis with move annotations (D12 / ROADMAP #16).

Walks every position in the current game's history, runs engine analysis at
depth 4, computes eval deltas, and annotates each move with a standard
symbol:
    !!  brilliant / best move that is also only or equal best
    !   best move (matches engine suggestion)
    ?!  inaccuracy (eval delta 50-150 cp)
    ?   mistake (delta 150-400 cp)
    ??  blunder (delta > 400 cp)
    (no mark) — normal move

The module contains:
    - annotate_move(delta_cp, is_best) -> str  — pure annotation logic
    - GameAnnotation dataclass
    - GameAnalyzer — does the heavy lifting without Qt
    - run_game_analysis(controller, parent_widget) — Qt entry point that
      shows a progress dialog, runs the analyzer in a thread, then shows
      results + the eval curve widget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

logger = logging.getLogger("draughts.game_analyzer")

if TYPE_CHECKING:
    from draughts.app.controller import GameController


# ---------------------------------------------------------------------------
# Pure annotation logic (no Qt, testable)
# ---------------------------------------------------------------------------

# Threshold constants in raw evaluate_position units.
# With tuned weights (_PAWN_VALUE ~1.9), losing one pawn ≈ 2 eval units.
# Previous values (50/150/400) were calibrated for _PAWN_VALUE=5.0 and
# never triggered in practice after Texel tuning reduced the eval scale.
_INACCURACY_MIN = 0.5  # ~0.25 pawns — slight inaccuracy
_MISTAKE_MIN = 1.5  # ~0.75 pawns — clear mistake
_BLUNDER_MIN = 4.0  # ~2 pawns — serious blunder


def annotate_move(delta_cp: float, is_best: bool) -> str:
    """Return annotation symbol for a move given its eval loss.

    Args:
        delta_cp: Non-negative eval loss in centipawn units.  0 = move was
            as good as the best move.  Positive = the move was worse by
            this many cp.
        is_best: True if the move played matches the engine's top suggestion.

    Returns:
        One of: "!!", "!", "?!", "?", "??", or "" (empty = normal).
    """
    if delta_cp < 0:
        delta_cp = 0.0

    if is_best:
        # Best move: either !! (only good move / unambiguously best) or !
        # We use !! only when the delta is 0 AND it is the only legal move
        # or a known sacrifice — for simplicity we just return "!" here;
        # callers that want !! can compare legal_move_count == 1.
        return "!"
    if delta_cp >= _BLUNDER_MIN:
        return "??"
    if delta_cp >= _MISTAKE_MIN:
        return "?"
    if delta_cp >= _INACCURACY_MIN:
        return "?!"
    return ""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class MoveAnnotation:
    """Annotation for a single half-move."""

    ply: int
    notation: str
    annotation: str  # "!!", "!", "?!", "?", "??", or ""
    eval_before: float  # engine eval before move (from side-to-move's POV)
    eval_after: float  # engine eval after move (from side-to-move's POV)
    best_notation: str  # engine's top move notation (may equal notation)
    delta_cp: float  # eval loss in cp (non-negative)


@dataclass
class GameAnalysisResult:
    """Full analysis result for the game."""

    annotations: list[MoveAnnotation] = field(default_factory=list)
    evals: list[float] = field(default_factory=list)  # one per half-move

    @property
    def blunder_count(self) -> int:
        return sum(1 for a in self.annotations if a.annotation == "??")

    @property
    def mistake_count(self) -> int:
        return sum(1 for a in self.annotations if a.annotation == "?")

    @property
    def inaccuracy_count(self) -> int:
        return sum(1 for a in self.annotations if a.annotation == "?!")

    def summary(self) -> str:
        parts = []
        if self.blunder_count:
            parts.append(f"{self.blunder_count} грубых ошибок")
        if self.mistake_count:
            parts.append(f"{self.mistake_count} ошибок")
        if self.inaccuracy_count:
            parts.append(f"{self.inaccuracy_count} неточностей")
        if not parts:
            return "Отличная игра! Ни одной ошибки."
        return ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Core analyzer (no Qt)
# ---------------------------------------------------------------------------

ANALYSIS_DEPTH = 4  # depth 4 keeps a 40-move game well under 60 s


def _notation_from_move(ai_move) -> str:
    """Convert an AIMove to algebraic notation string."""
    from draughts.game.board import Board

    if ai_move is None:
        return "—"
    sep = ":" if ai_move.kind == "capture" else "-"
    return sep.join(Board.pos_to_notation(x, y) for x, y in ai_move.path)


def analyze_game_positions(
    positions: list[str],
    depth: int = ANALYSIS_DEPTH,
    progress_callback=None,
    start_color=None,
    should_cancel=None,
) -> GameAnalysisResult:
    """Analyze a list of position strings (game history) and return annotations.

    Args:
        positions: List of position strings from controller._positions.
            positions[0] is the start; positions[i+1] is after ply i.
        depth: AI search depth (default 4).
        progress_callback: Optional callable(current, total) for progress.
        start_color: Side to move at positions[0]. Defaults to White
            (standard opening). Must be supplied for games loaded from
            a FEN-carrying PDN where Black moves first — otherwise every
            ply's colour is inverted, yielding wrong eval deltas, wrong
            "best move" comparisons, and blunder annotations attached
            to the wrong side.
        should_cancel: Optional zero-arg callable returning ``True`` when
            the caller (e.g. a Qt progress dialog) wants the analysis to
            stop early. Checked at each ply boundary; on cancel the
            function returns whatever annotations were produced so far.
            Without this hook the Qt dialog's "Cancel" button could only
            suppress progress-bar updates while the search continued to
            completion (P3 flagged by audit #4).

    Returns:
        GameAnalysisResult with per-move annotations and eval curve data.
    """
    from draughts.config import Color
    from draughts.game.analysis import get_ai_analysis
    from draughts.game.board import Board
    from draughts.game.headless import HeadlessGame

    result = GameAnalysisResult()

    n_moves = len(positions) - 1  # number of half-moves
    if n_moves <= 0:
        return result

    if start_color is None:
        start_color = Color.WHITE

    for ply in range(n_moves):
        if should_cancel is not None and should_cancel():
            return result
        if progress_callback is not None:
            progress_callback(ply, n_moves)

        pos_before = positions[ply]
        pos_after = positions[ply + 1]

        # Side to move at ``ply``: alternates from ``start_color``.
        color = start_color if ply % 2 == 0 else start_color.opponent

        # Analyze position BEFORE the move was played
        hg_before = HeadlessGame(position=pos_before, auto_ai=False)
        hg_before._turn = color
        try:
            analysis_before = get_ai_analysis(hg_before, depth=depth)
        except Exception:
            logger.exception("Analysis failed at ply %d", ply)
            continue

        # Analyze position AFTER the move (from opponent's POV to get delta)
        # We compare: engine_score_before vs eval of position after move.
        # Both from the same side's POV (negate after, since board flips).
        hg_after = HeadlessGame(position=pos_after, auto_ai=False)
        opp = color.opponent
        hg_after._turn = opp
        try:
            analysis_after = get_ai_analysis(hg_after, depth=depth)
        except Exception:
            logger.exception("Analysis failed at ply %d (after)", ply)
            continue

        # eval_before: engine best score from side-to-move's POV
        eval_before = analysis_before.score

        # eval_after from opponent's POV — negate to get from our side's POV
        eval_after_ours = -analysis_after.score

        # Delta: how much worse than the best line did we play?
        # Positive = we lost cp relative to best.
        delta_cp = max(0.0, eval_before - eval_after_ours)

        # Reconstruct what move was actually played
        board_before = Board()
        board_before.load_from_position_string(pos_before)
        board_after_obj = Board()
        board_after_obj.load_from_position_string(pos_after)

        # Infer notation from the board diff. _infer_pdn_move_from_boards
        # returns the PDN numeric form (e.g. '22x15'); convert to
        # algebraic so both played_notation and best_notation use the
        # same convention (CLAUDE.md requires algebraic a1..h8 across
        # UI, CLI, and logs).
        from draughts.app.controller import _infer_pdn_move_from_boards
        from draughts.game.pdn import pdn_move_to_notation

        played_pdn = _infer_pdn_move_from_boards(board_before, board_after_obj)
        if played_pdn:
            try:
                played_notation = pdn_move_to_notation(played_pdn)
            except ValueError:
                played_notation = played_pdn  # fall back rather than hide the move
        else:
            played_notation = f"ход {ply + 1}"

        # Best move notation in algebraic form (same format as _notation_from_move)
        best_notation = _notation_from_move(analysis_before.best_move)

        # Compare moves by applying best move and checking if positions match,
        # since string comparison across notations would miss equivalent
        # moves; delta_cp is a secondary check for functionally
        # equivalent near-best plays.
        is_best = False
        if analysis_before.best_move is not None:
            try:
                test_board = board_before.copy()
                bm = analysis_before.best_move
                if bm.kind == "capture":
                    test_board.execute_capture_path(bm.path)
                else:
                    x1, y1 = bm.path[0]
                    x2, y2 = bm.path[1]
                    test_board.execute_move(x1, y1, x2, y2)
                is_best = test_board.to_position_string() == pos_after
            except Exception:
                pass
        # Fallback: if delta is negligible, treat as best (within ~0.1 pawn)
        if not is_best and delta_cp < _INACCURACY_MIN:
            is_best = True

        annotation = annotate_move(delta_cp, is_best)

        move_ann = MoveAnnotation(
            ply=ply,
            notation=played_notation,
            annotation=annotation,
            eval_before=eval_before,
            eval_after=eval_after_ours,
            best_notation=best_notation,
            delta_cp=delta_cp,
        )
        result.annotations.append(move_ann)
        result.evals.append(eval_before)

    # Final eval point
    if positions:
        try:
            hg_final = HeadlessGame(position=positions[-1], auto_ai=False)
            last_color = start_color if n_moves % 2 == 0 else start_color.opponent
            hg_final._turn = last_color
            final_analysis = get_ai_analysis(hg_final, depth=depth)
            result.evals.append(final_analysis.score)
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Qt entry point
# ---------------------------------------------------------------------------


def run_game_analysis(controller: GameController, parent=None) -> None:
    """Launch full-game analysis: progress dialog → annotations → summary."""
    from PyQt6.QtCore import QObject, QThread, pyqtSignal
    from PyQt6.QtWidgets import QMessageBox, QProgressDialog

    from draughts.config import Color

    positions = list(controller._positions)
    if len(positions) < 2:
        QMessageBox.information(parent, "Анализ партии", "Партия ещё не начата.")
        return

    # Side-to-move at positions[0]. FEN-loaded PDN games may start with
    # Black to move — without this, every ply's colour is inverted and
    # blunder annotations attach to the wrong side.
    start_color = getattr(controller, "_game_start_color", Color.WHITE)

    n_moves = len(positions) - 1

    # --- Progress dialog ---
    progress = QProgressDialog("Анализирую партию…", "Отмена", 0, n_moves, parent)
    progress.setWindowTitle("Анализ партии")
    progress.setMinimumDuration(0)
    progress.setValue(0)

    # Worker running analysis in a thread
    class _Worker(QObject):
        progress_updated = pyqtSignal(int, int)
        finished = pyqtSignal(object)

        def __init__(self, positions_: list[str], start_color_):
            super().__init__()
            self._positions = positions_
            self._start_color = start_color_
            self._cancelled = False

        def cancel(self):
            self._cancelled = True

        def run(self):
            def _cb(current, total):
                if self._cancelled:
                    return
                self.progress_updated.emit(current, total)

            try:
                result = analyze_game_positions(
                    self._positions,
                    progress_callback=_cb,
                    start_color=self._start_color,
                    should_cancel=lambda: self._cancelled,
                )
            except Exception:
                logger.exception("Game analysis worker crashed")
                result = GameAnalysisResult()
            self.finished.emit(result)

    thread = QThread()
    worker = _Worker(positions, start_color)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.progress_updated.connect(lambda cur, total: progress.setValue(cur))
    worker.finished.connect(
        lambda r: _on_analysis_done(r, controller, parent, progress, thread, worker, start_color)
    )
    progress.canceled.connect(worker.cancel)
    thread.start()
    progress.exec()


def _on_analysis_done(
    result: GameAnalysisResult,
    controller,
    parent,
    progress,
    thread,
    worker,
    start_color=None,
) -> None:
    """Called when analysis thread finishes -- show results.

    ``start_color`` is the side-to-move at positions[0]; passed through
    so the (ply → move number) pairing in the display matches the game
    (otherwise a black-starting FEN game would show "1. — black_move"
    shifted by one). Defaults to White for backward compatibility.
    """
    from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

    from draughts.config import Color
    from draughts.ui.theme_engine import apply_theme as _apply_engine_theme
    from draughts.ui.theme_engine import get_theme_colors

    if start_color is None:
        start_color = Color.WHITE

    progress.close()
    thread.quit()
    thread.wait()
    worker.deleteLater()
    thread.deleteLater()

    # Store annotations on controller for access by other UI elements
    controller._last_game_analysis = result

    # Resolve theme colors
    theme_name = getattr(controller.settings, "board_theme", "dark_wood")
    tc = get_theme_colors(theme_name)

    # --- Build result dialog ---
    dlg = QDialog(parent)
    dlg.setWindowTitle("Результаты анализа")
    dlg.resize(560, 600)
    _apply_engine_theme(dlg, theme_name)

    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(12, 12, 12, 12)
    outer.setSpacing(8)

    # Summary line
    summary_lbl = QLabel(result.summary())
    summary_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {tc['fg_accent']};")
    summary_lbl.setWordWrap(True)
    outer.addWidget(summary_lbl)

    # Eval curve
    from draughts.ui.eval_curve import EvalCurveWidget

    curve = EvalCurveWidget(theme_name=theme_name)
    curve.set_evals(result.evals)
    curve.setMinimumHeight(100)
    curve.setMaximumHeight(130)
    outer.addWidget(curve)

    # Move list with annotations
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {tc['scroll_bg']}; }}")
    move_container = QWidget()
    move_container.setStyleSheet(f"background: {tc['scroll_bg']};")
    move_layout = QVBoxLayout(move_container)
    move_layout.setContentsMargins(8, 8, 8, 8)
    move_layout.setSpacing(2)

    annotation_colors = {
        "!!": tc["ann_brilliant"],
        "!": tc["ann_good"],
        "?!": tc["ann_inaccuracy"],
        "?": tc["ann_mistake"],
        "??": tc["ann_blunder"],
        "": tc["ann_normal"],
    }

    # Group into pairs (white + black per move number).
    # For a black-starting FEN game, ply 0 is black's and the first row
    # must be emitted as "1. … black_move" with an empty white slot.
    annotations = result.annotations
    i = 0
    move_num = 1
    starts_with_black = start_color == Color.BLACK
    while i < len(annotations):
        if starts_with_black and move_num == 1 and i == 0:
            # First printed row: no white move, black's ply 0 goes right.
            white_ann = None
            black_ann = annotations[0]
            consumed = 1
        else:
            white_ann = annotations[i] if i < len(annotations) else None
            black_ann = annotations[i + 1] if i + 1 < len(annotations) else None
            consumed = 2

        row = QHBoxLayout()
        num_lbl = QLabel(f"{move_num}.")
        num_lbl.setStyleSheet(f"color: {tc['ann_move_num']}; font-size: 12px; min-width: 28px;")
        row.addWidget(num_lbl)

        for ann in (white_ann, black_ann):
            if ann is None:
                row.addStretch()
                continue
            sym = ann.annotation
            color = annotation_colors.get(sym, tc["ann_normal"])
            text = f"{ann.notation}{sym}"
            if sym in ("?", "?!", "??"):
                tip = f"Потеря: {ann.delta_cp:.0f} ед.  Лучше: {ann.best_notation}"
            else:
                tip = f"Оценка: {ann.eval_before:.0f}"
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
            lbl.setToolTip(tip)
            row.addWidget(lbl)

        row.addStretch()
        wrapper = QWidget()
        wrapper.setLayout(row)
        move_layout.addWidget(wrapper)

        i += consumed
        move_num += 1

    move_layout.addStretch()
    scroll.setWidget(move_container)
    outer.addWidget(scroll)

    # Close button (styled by the dialog-level QSS from theme engine)
    btn_close = QPushButton("Закрыть")
    btn_close.clicked.connect(dlg.accept)
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_row.addWidget(btn_close)
    outer.addLayout(btn_row)

    dlg.exec()

    # --- Puzzle mining ---
    _offer_puzzle_mining(result, list(controller._positions), parent, start_color=start_color)


def _offer_puzzle_mining(
    result: GameAnalysisResult,
    positions: list[str],
    parent,
    start_color=None,
) -> None:
    """If the game contains blunders, offer to mine them as puzzles.

    ``start_color`` is forwarded to :func:`mine_puzzles_from_game` so that
    the "turn" field on each puzzle matches the side that actually moved
    at the blunder ply. Defaults to White.
    """
    from PyQt6.QtWidgets import QMessageBox

    from draughts.config import Color
    from draughts.game.puzzle_miner import append_mined_puzzles, mine_puzzles_from_game

    if start_color is None:
        start_color = Color.WHITE

    if result.blunder_count == 0:
        return

    candidates = mine_puzzles_from_game(
        positions, result.annotations, start_color=start_color
    )
    if not candidates:
        return

    n = len(candidates)
    reply = QMessageBox.question(
        parent,
        "Задачи из партии",
        f"Найдено {n} {'позиция' if n == 1 else 'позиции' if n < 5 else 'позиций'} для тренировки.\n"
        "Добавить в коллекцию задач?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    added = append_mined_puzzles(candidates)
    if added > 0:
        QMessageBox.information(
            parent,
            "Задачи добавлены",
            f"Добавлено {added} {'задача' if added == 1 else 'задачи' if added < 5 else 'задач'} в личную коллекцию.",
        )
    else:
        QMessageBox.information(
            parent,
            "Задачи добавлены",
            "Все найденные позиции уже есть в коллекции.",
        )
