"""Analysis pane — dockable widget for live engine analysis (D12 / ROADMAP #15).

Shows the engine thinking about the current position in a background thread.
Toggle with F3 from the main window.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from draughts.config import Color
    from draughts.game.analysis import Analysis
    from draughts.game.board import Board

from draughts.ui.theme_engine import get_theme_colors as _get_theme_colors

logger = logging.getLogger("draughts.analysis_pane")


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


class AnalysisWorker(QObject):
    """Runs engine analysis in a background thread.

    Emits ``finished`` with an ``Analysis`` result when done,
    or ``None`` if analysis could not complete.
    """

    finished = pyqtSignal(object)  # Analysis | None

    def __init__(self, board: Board, color: Color, time_ms: int = 3000):
        super().__init__()
        self._board = board
        self._color = color
        self._time_ms = time_ms

    def run(self) -> None:
        try:
            # Build an Analysis-like result using a single depth-limited search.
            # Previously this ran find_move_timed AND _search_best_move, doing
            # the work twice and discarding the first result (BUG-006).
            from draughts.game.ai import _generate_all_moves, _search_best_move, adaptive_depth, evaluate_position
            from draughts.game.ai.state import SearchContext
            from draughts.game.analysis import Analysis

            moves = _generate_all_moves(self._board, self._color)
            effective_depth = adaptive_depth(6, self._board)
            static = evaluate_position(self._board.grid, self._color)

            ctx = SearchContext()
            t0 = time.perf_counter()
            best = _search_best_move(self._board, self._color, effective_depth, ctx=ctx)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            search_score = ctx.last_score if best is not None else static

            result = Analysis(
                best_move=best,
                score=search_score,
                static_score=static,
                depth=effective_depth,
                legal_move_count=len(moves),
            )
            # Attach elapsed time so the pane can display it
            result._elapsed_ms = elapsed_ms  # type: ignore[attr-defined]
        except Exception:
            logger.exception("AnalysisWorker crashed")
            result = None
        self.finished.emit(result)


# ---------------------------------------------------------------------------
# Analysis pane widget
# ---------------------------------------------------------------------------


class AnalysisPane(QDockWidget):
    """Side pane that displays engine analysis of the current position.

    Dockable to the right side of the main window. Toggle with F3.
    Auto-updates when the board position changes (unless the game engine
    is already thinking).
    """

    #: Emitted when the pane finishes an analysis pass
    analysis_done = pyqtSignal(object)  # Analysis | None

    def __init__(self, parent=None):
        super().__init__("Анализ позиции", parent)
        # Theme colors are applied via the parent window's QSS cascade
        self._tc = _get_theme_colors("dark_wood")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._thread: QThread | None = None
        self._worker: AnalysisWorker | None = None
        self._current_board = None
        self._current_color = None
        self._is_running = False

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        tc = self._tc
        _label_style = f"color: {tc['fg']}; font-size: 12px;"
        _value_style = f"color: {tc['fg_accent']}; font-size: 12px; font-weight: bold;"
        _caption_style = f"color: {tc['caption_fg']}; font-size: 11px;"

        container = QWidget()
        container.setStyleSheet(f"background-color: {tc['bg']};")
        self.setWidget(container)

        outer = QVBoxLayout(container)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        # --- Score row ---
        score_row = QHBoxLayout()
        score_lbl = QLabel("Оценка:")
        score_lbl.setStyleSheet(_label_style)
        score_row.addWidget(score_lbl)
        self._score_val = QLabel("—")
        self._score_val.setStyleSheet(_value_style)
        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(14)
        self._score_val.setFont(bold)
        score_row.addWidget(self._score_val)
        score_row.addStretch()
        outer.addLayout(score_row)

        # --- Best move row ---
        bm_row = QHBoxLayout()
        bm_lbl = QLabel("Лучший ход:")
        bm_lbl.setStyleSheet(_label_style)
        bm_row.addWidget(bm_lbl)
        self._bm_val = QLabel("—")
        self._bm_val.setStyleSheet(_value_style)
        bm_row.addWidget(self._bm_val)
        bm_row.addStretch()
        outer.addLayout(bm_row)

        # --- Depth row ---
        depth_row = QHBoxLayout()
        depth_lbl = QLabel("Глубина:")
        depth_lbl.setStyleSheet(_label_style)
        depth_row.addWidget(depth_lbl)
        self._depth_val = QLabel("—")
        self._depth_val.setStyleSheet(_value_style)
        depth_row.addWidget(self._depth_val)
        depth_row.addStretch()
        outer.addLayout(depth_row)

        # --- Time row ---
        time_row = QHBoxLayout()
        time_lbl = QLabel("Время:")
        time_lbl.setStyleSheet(_label_style)
        time_row.addWidget(time_lbl)
        self._time_val = QLabel("—")
        self._time_val.setStyleSheet(_value_style)
        time_row.addWidget(self._time_val)
        time_row.addStretch()
        outer.addLayout(time_row)

        # --- Legal moves row ---
        lm_row = QHBoxLayout()
        lm_lbl = QLabel("Ходов:")
        lm_lbl.setStyleSheet(_label_style)
        lm_row.addWidget(lm_lbl)
        self._lm_val = QLabel("—")
        self._lm_val.setStyleSheet(_value_style)
        lm_row.addWidget(self._lm_val)
        lm_row.addStretch()
        outer.addLayout(lm_row)

        # --- Status label ---
        self._status_lbl = QLabel("Нажмите «Анализ» для запуска")
        self._status_lbl.setStyleSheet(_caption_style)
        self._status_lbl.setWordWrap(True)
        outer.addWidget(self._status_lbl)

        outer.addStretch()

        # --- Buttons ---
        btn_row = QHBoxLayout()
        self._btn_run = QPushButton("Анализ")
        self._btn_run.setStyleSheet(
            f"QPushButton {{ background: {tc['analysis_run_bg']}; color: {tc['fg']}; "
            f"border: 1px solid {tc['analysis_run_border']}; "
            f"border-radius: 3px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ background: {tc['analysis_run_hover']}; }}"
            f"QPushButton:disabled {{ background: {tc['disabled_bg']}; color: {tc['disabled_fg']}; }}"
        )
        self._btn_run.clicked.connect(self._on_run_clicked)
        btn_row.addWidget(self._btn_run)

        self._btn_stop = QPushButton("Стоп")
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet(
            f"QPushButton {{ background: {tc['analysis_stop_bg']}; color: {tc['fg']}; "
            f"border: 1px solid {tc['analysis_stop_border']}; "
            f"border-radius: 3px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ background: {tc['analysis_stop_hover']}; }}"
            f"QPushButton:disabled {{ background: {tc['disabled_bg']}; color: {tc['disabled_fg']}; }}"
        )
        self._btn_stop.clicked.connect(self._on_stop_clicked)
        btn_row.addWidget(self._btn_stop)
        outer.addLayout(btn_row)

        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_position(self, board: Board, color: Color) -> None:
        """Update the position that will be analyzed on the next run."""
        self._current_board = board
        self._current_color = color

    def request_analysis(self, board: Board | None = None, color: Color | None = None) -> None:
        """Start analysis, optionally updating position first."""
        if board is not None:
            self._current_board = board
        if color is not None:
            self._current_color = color
        self._start_analysis()

    def stop_analysis(self) -> None:
        """Stop any running analysis thread."""
        self._stop_thread()

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_run_clicked(self) -> None:
        self._start_analysis()

    def _on_stop_clicked(self) -> None:
        self._stop_thread()
        self._status_lbl.setText("Остановлено")
        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)

    def _on_analysis_finished(self, result: Analysis | None) -> None:
        self._is_running = False
        self._cleanup_thread()

        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)

        if result is None:
            self._status_lbl.setText("Ошибка анализа")
            return

        # Update labels
        score = result.score
        if abs(score) >= 9000:
            score_text = "Мат" if score > 0 else "-Мат"
        else:
            # Display as centi-pawns * 100 for readability
            sign = "+" if score >= 0 else ""
            score_text = f"{sign}{score:.0f}"
        self._score_val.setText(score_text)

        if result.best_move is not None:
            from draughts.game.board import Board

            sep = ":" if result.best_move.kind == "capture" else "-"
            move_str = sep.join(Board.pos_to_notation(x, y) for x, y in result.best_move.path)
            self._bm_val.setText(move_str)
        else:
            self._bm_val.setText("нет ходов")

        self._depth_val.setText(str(result.depth))
        self._lm_val.setText(str(result.legal_move_count))

        elapsed_ms = getattr(result, "_elapsed_ms", None)
        if elapsed_ms is not None:
            self._time_val.setText(f"{elapsed_ms / 1000.0:.2f} с")
        else:
            self._time_val.setText("—")

        self._status_lbl.setText("Готово")
        self.analysis_done.emit(result)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_analysis(self) -> None:
        if self._current_board is None or self._current_color is None:
            self._status_lbl.setText("Позиция не задана")
            return
        if self._is_running:
            return

        self._stop_thread()

        self._is_running = True
        self._btn_run.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._status_lbl.setText("Анализирую…")
        # Reset display to indicate stale values
        self._score_val.setText("…")
        self._bm_val.setText("…")
        self._depth_val.setText("…")
        self._time_val.setText("…")

        self._thread = QThread()
        self._worker = AnalysisWorker(
            self._current_board.copy(),
            self._current_color,
            time_ms=3000,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_analysis_finished)
        self._thread.start()

    def _stop_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(500)
            self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            try:
                self._worker.deleteLater()
            except RuntimeError:
                pass
            self._worker = None
        if self._thread is not None:
            try:
                self._thread.deleteLater()
            except RuntimeError:
                pass
            self._thread = None
        self._is_running = False
