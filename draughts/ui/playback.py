"""Playback widget — animated review of a saved game, move by move."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from draughts.game.board import Board
from draughts.ui.board_widget import BoardWidget


class PlaybackDialog(QDialog):
    """Modal dialog for reviewing a game move by move."""

    def __init__(self, positions: list[str], parent=None):
        """Create the playback dialog.

        Args:
            positions: List of 32-char board state strings (one per half-move).
        """
        super().__init__(parent)
        self.setWindowTitle("Просмотр партии")
        self.setModal(True)
        self.resize(600, 520)

        # Apply theme from parent window
        current_theme = "dark_wood"
        if parent is not None and hasattr(parent, "_current_theme"):
            current_theme = parent._current_theme
        from draughts.ui.theme_engine import apply_theme as _apply_engine_theme

        _apply_engine_theme(self, current_theme)

        self._positions = positions
        self._current = 0
        self._playing = False

        self._build_ui()
        self._show_position(0)

        # Auto-play timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step_forward)
        self._play_interval = 1000  # ms between moves

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Board widget
        self._board_widget = BoardWidget()
        self._board_widget.setMinimumSize(400, 400)
        layout.addWidget(self._board_widget, stretch=1)

        # Position indicator
        self._label = QLabel("Ход 0 / 0")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        layout.addWidget(self._label)

        # Slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(max(0, len(self._positions) - 1))
        self._slider.setValue(0)
        self._slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self._slider)

        # Control buttons
        btn_layout = QHBoxLayout()

        self._btn_start = QPushButton("⏮ Начало")
        self._btn_start.clicked.connect(self._go_start)
        btn_layout.addWidget(self._btn_start)

        self._btn_prev = QPushButton("◀ Назад")
        self._btn_prev.clicked.connect(self._step_back)
        btn_layout.addWidget(self._btn_prev)

        self._btn_play = QPushButton("▶ Воспроизвести")
        self._btn_play.clicked.connect(self._toggle_play)
        btn_layout.addWidget(self._btn_play)

        self._btn_next = QPushButton("Вперёд ▶")
        self._btn_next.clicked.connect(self._step_forward)
        btn_layout.addWidget(self._btn_next)

        self._btn_end = QPushButton("Конец ⏭")
        self._btn_end.clicked.connect(self._go_end)
        btn_layout.addWidget(self._btn_end)

        layout.addLayout(btn_layout)

        # Close button
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _show_position(self, index: int):
        """Display the board state at the given index."""
        if not self._positions or index < 0 or index >= len(self._positions):
            return

        self._current = index
        board = Board(empty=True)
        board.load_from_position_string(self._positions[index])
        self._board_widget.set_board(board)
        self._board_widget.set_selection()

        total = len(self._positions) - 1
        self._label.setText(f"Ход {index} / {total}")
        self._slider.blockSignals(True)
        self._slider.setValue(index)
        self._slider.blockSignals(False)

        self._update_buttons()

    def _update_buttons(self):
        at_start = self._current == 0
        at_end = self._current >= len(self._positions) - 1

        self._btn_start.setEnabled(not at_start)
        self._btn_prev.setEnabled(not at_start)
        self._btn_next.setEnabled(not at_end)
        self._btn_end.setEnabled(not at_end)

        if at_end and self._playing:
            self._stop_play()

    def _step_forward(self):
        if self._current < len(self._positions) - 1:
            self._show_position(self._current + 1)

    def _step_back(self):
        if self._current > 0:
            self._show_position(self._current - 1)

    def _go_start(self):
        self._stop_play()
        self._show_position(0)

    def _go_end(self):
        self._stop_play()
        self._show_position(len(self._positions) - 1)

    def _toggle_play(self):
        if self._playing:
            self._stop_play()
        else:
            self._start_play()

    def _start_play(self):
        if self._current >= len(self._positions) - 1:
            self._show_position(0)
        self._playing = True
        self._btn_play.setText("⏸ Пауза")
        self._timer.start(self._play_interval)

    def _stop_play(self):
        self._playing = False
        self._btn_play.setText("▶ Воспроизвести")
        self._timer.stop()

    def _on_slider_changed(self, value: int):
        self._show_position(value)

    def closeEvent(self, event):
        self._stop_play()
        event.accept()
