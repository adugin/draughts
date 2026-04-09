"""Main window for the Draughts application."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QPushButton, QLabel, QTextEdit, QFrame, QSizePolicy,
)

from draughts.config import COLORS, BTN_LABELS
from draughts.game.board import Board
from draughts.ui.board_widget import BoardWidget


class MainWindow(QMainWindow):
    """Main application window with board, controls, and status panels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Шашки")
        self.setMinimumSize(640, 480)
        self.resize(900, 660)

        self._build_ui()
        self._start_clock()

        # Set initial board
        board = Board()
        self.board_widget.set_board(board)

    def _build_ui(self):
        """Construct the complete UI layout."""
        central = QWidget()
        self.setCentralWidget(central)

        # Top-level: board (left) + right panel, then bottom panel below
        outer_v = QVBoxLayout(central)
        outer_v.setContentsMargins(4, 4, 4, 4)
        outer_v.setSpacing(4)

        # Header label
        self.header_label = QLabel("Автор и разработчик программы: Дугин Андрей")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_label.setStyleSheet(
            f"background-color: rgb{COLORS['panel_bg']}; "
            f"color: rgb{COLORS['window_title']}; "
            "font-weight: bold; padding: 2px; "
            "border: 1px solid gray;"
        )
        self.header_label.setFixedHeight(24)
        outer_v.addWidget(self.header_label)

        # Main area: board + right panel
        main_h = QHBoxLayout()
        main_h.setSpacing(4)

        # --- Board widget ---
        self.board_widget = BoardWidget()
        self.board_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_h.addWidget(self.board_widget, stretch=3)

        # --- Right panel ---
        right_panel = QFrame()
        right_panel.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        right_panel.setLineWidth(1)
        right_panel.setStyleSheet(f"QFrame {{ background-color: rgb{COLORS['panel_bg']}; }}")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(4)

        # Turn indicator (sample pieces)
        turn_row = QHBoxLayout()
        self.white_indicator = QLabel("  White  ")
        self.white_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.white_indicator.setStyleSheet(
            "background-color: white; color: black; "
            "border: 2px solid gray; font-weight: bold; padding: 4px;"
        )
        self.black_indicator = QLabel("  Black  ")
        self.black_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.black_indicator.setStyleSheet(
            "background-color: black; color: white; "
            "border: 2px solid gray; font-weight: bold; padding: 4px;"
        )
        turn_row.addWidget(self.white_indicator)
        turn_row.addWidget(self.black_indicator)
        right_layout.addLayout(turn_row)

        # Move notation area (two columns)
        notation_label = QLabel("Нотация ходов")
        notation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notation_label.setStyleSheet("font-weight: bold; background: transparent;")
        right_layout.addWidget(notation_label)

        notation_row = QHBoxLayout()

        self.notation_white = QTextEdit()
        self.notation_white.setReadOnly(True)
        self.notation_white.setPlaceholderText("Белые")
        self.notation_white.setStyleSheet("background-color: white; font-family: Consolas, monospace;")
        self.notation_white.setMaximumWidth(200)

        self.notation_black = QTextEdit()
        self.notation_black.setReadOnly(True)
        self.notation_black.setPlaceholderText("Чёрные")
        self.notation_black.setStyleSheet("background-color: white; font-family: Consolas, monospace;")
        self.notation_black.setMaximumWidth(200)

        notation_row.addWidget(self.notation_white)
        notation_row.addWidget(self.notation_black)
        right_layout.addLayout(notation_row, stretch=1)

        # Buttons (9 buttons from config)
        self.buttons: dict[str, QPushButton] = {}
        btn_grid = QGridLayout()
        btn_grid.setSpacing(3)
        for i, label in enumerate(BTN_LABELS):
            btn = QPushButton(label)
            btn.setMinimumHeight(26)
            btn.setStyleSheet(
                "QPushButton { background-color: rgb(192,192,192); "
                "border: 2px outset rgb(220,220,220); padding: 2px 6px; }"
                "QPushButton:pressed { border-style: inset; }"
            )
            self.buttons[label] = btn
            # Layout: 2 columns for first 8, last one spans full width
            if i < 8:
                btn_grid.addWidget(btn, i // 2, i % 2)
            else:
                btn_grid.addWidget(btn, i // 2, 0, 1, 2)
        right_layout.addLayout(btn_grid)

        # Timer display
        self.timer_label = QLabel("00:30")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; font-family: Consolas, monospace; "
            "background-color: white; border: 1px solid gray; padding: 4px;"
        )
        right_layout.addWidget(self.timer_label)

        # Clock and date
        self.clock_label = QLabel("00:00:00")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet(
            "font-size: 14px; font-family: Consolas, monospace; "
            "background-color: white; border: 1px solid gray; padding: 2px;"
        )
        self.date_label = QLabel("")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet(
            "font-size: 12px; font-family: Consolas, monospace; "
            "background-color: white; border: 1px solid gray; padding: 2px;"
        )
        right_layout.addWidget(self.clock_label)
        right_layout.addWidget(self.date_label)

        right_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right_panel.setMinimumWidth(200)
        main_h.addWidget(right_panel, stretch=2)

        outer_v.addLayout(main_h, stretch=1)

        # --- Bottom panel ---
        bottom_panel = QFrame()
        bottom_panel.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        bottom_panel.setLineWidth(1)
        bp_bg = COLORS['bottom_panel_bg']
        bottom_panel.setStyleSheet(
            f"QFrame {{ background-color: rgb({bp_bg[0]},{bp_bg[1]},{bp_bg[2]}); }}"
        )
        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(6, 4, 6, 4)
        bottom_layout.setSpacing(8)

        # Captured pieces display
        self.captured_label = QLabel("")
        self.captured_label.setStyleSheet(
            "color: white; font-size: 14px; background: transparent;"
        )
        bottom_layout.addWidget(self.captured_label, stretch=1)

        # Message area (AI thinking messages)
        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setStyleSheet(
            "color: rgb(0,255,0); font-size: 13px; "
            "font-style: italic; background: transparent;"
        )
        bottom_layout.addWidget(self.message_label, stretch=2)

        bottom_panel.setFixedHeight(70)
        outer_v.addWidget(bottom_panel)

    # --- Clock / timer ---

    def _start_clock(self):
        """Start a 1-second timer to update clock and date display."""
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = datetime.now()
        self.clock_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(now.strftime("%d.%m.%Y"))

    # --- Public convenience methods ---

    def set_message(self, text: str):
        """Display a message in the bottom panel."""
        self.message_label.setText(text)

    def set_captured_display(self, text: str):
        """Update the captured pieces display."""
        self.captured_label.setText(text)

    def set_timer_display(self, seconds: int):
        """Update the countdown timer display."""
        mins = seconds // 60
        secs = seconds % 60
        self.timer_label.setText(f"{mins:02d}:{secs:02d}")

    def highlight_turn(self, color: str):
        """Visually indicate whose turn it is."""
        if color == 'w':
            self.white_indicator.setStyleSheet(
                "background-color: white; color: black; "
                "border: 3px solid rgb(0,255,0); font-weight: bold; padding: 4px;"
            )
            self.black_indicator.setStyleSheet(
                "background-color: black; color: white; "
                "border: 2px solid gray; font-weight: bold; padding: 4px;"
            )
        else:
            self.white_indicator.setStyleSheet(
                "background-color: white; color: black; "
                "border: 2px solid gray; font-weight: bold; padding: 4px;"
            )
            self.black_indicator.setStyleSheet(
                "background-color: black; color: white; "
                "border: 3px solid rgb(0,255,0); font-weight: bold; padding: 4px;"
            )
        self.board_widget.set_turn_indicator(color)

    def append_notation(self, move_text: str, color: str):
        """Append a move to the notation panel."""
        if color == 'w':
            self.notation_white.append(move_text)
        else:
            self.notation_black.append(move_text)

    def clear_notation(self):
        """Clear both notation columns."""
        self.notation_white.clear()
        self.notation_black.clear()
