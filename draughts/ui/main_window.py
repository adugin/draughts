"""Main window for the Draughts application."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QPushButton, QLabel, QTextEdit, QFrame, QSizePolicy,
)

from draughts.config import COLORS, BTN_LABELS
from draughts.game.board import Board
from draughts.ui.board_widget import BoardWidget
from draughts.ui.captured_widget import CapturedWidget

if TYPE_CHECKING:
    from draughts.game.controller import GameController


class MainWindow(QMainWindow):
    """Main application window with board, controls, and status panels."""

    def __init__(self, controller: GameController, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Шашки")
        self.setMinimumSize(640, 480)
        self.resize(900, 660)

        self._controller = controller

        self._build_ui()
        self._start_clock()
        self._connect_controller()

    def _build_ui(self):
        """Construct the complete UI layout."""
        central = QWidget()
        self.setCentralWidget(central)

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
        self.header_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_label.mousePressEvent = lambda e: self._on_about()
        outer_v.addWidget(self.header_label)

        # Main area: board + right panel
        main_h = QHBoxLayout()
        main_h.setSpacing(4)

        # --- Board widget ---
        self.board_widget = BoardWidget()
        self.board_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_h.addWidget(self.board_widget, stretch=3)

        # --- Right panel ---
        right_panel = QFrame()
        right_panel.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        right_panel.setLineWidth(1)
        right_panel.setStyleSheet(
            f"QFrame {{ background-color: rgb{COLORS['panel_bg']}; }}")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(4)

        # Turn indicator
        turn_row = QHBoxLayout()
        self.white_indicator = QLabel("  Белые  ")
        self.white_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.white_indicator.setStyleSheet(
            "background-color: white; color: black; "
            "border: 2px solid gray; font-weight: bold; padding: 4px;")
        self.black_indicator = QLabel("  Чёрные  ")
        self.black_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.black_indicator.setStyleSheet(
            "background-color: black; color: white; "
            "border: 2px solid gray; font-weight: bold; padding: 4px;")
        turn_row.addWidget(self.white_indicator)
        turn_row.addWidget(self.black_indicator)
        right_layout.addLayout(turn_row)

        # Notation
        notation_label = QLabel("Нотация ходов")
        notation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notation_label.setStyleSheet(
            "font-weight: bold; background: transparent;")
        right_layout.addWidget(notation_label)

        notation_row = QHBoxLayout()
        self.notation_white = QTextEdit()
        self.notation_white.setReadOnly(True)
        self.notation_white.setPlaceholderText("Белые")
        self.notation_white.setStyleSheet(
            "background-color: white; font-family: Consolas, monospace;")
        self.notation_white.setMaximumWidth(200)

        self.notation_black = QTextEdit()
        self.notation_black.setReadOnly(True)
        self.notation_black.setPlaceholderText("Чёрные")
        self.notation_black.setStyleSheet(
            "background-color: white; font-family: Consolas, monospace;")
        self.notation_black.setMaximumWidth(200)

        notation_row.addWidget(self.notation_white)
        notation_row.addWidget(self.notation_black)
        right_layout.addLayout(notation_row, stretch=1)

        # Buttons
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
                "QPushButton:disabled { color: gray; }")
            self.buttons[label] = btn
            if i < 8:
                btn_grid.addWidget(btn, i // 2, i % 2)
            else:
                btn_grid.addWidget(btn, i // 2, 0, 1, 2)
        right_layout.addLayout(btn_grid)

        # Timer
        self.timer_label = QLabel("00:30")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; "
            "font-family: Consolas, monospace; "
            "background-color: white; border: 1px solid gray; padding: 4px;")
        right_layout.addWidget(self.timer_label)

        # Clock and date
        self.clock_label = QLabel("00:00:00")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet(
            "font-size: 14px; font-family: Consolas, monospace; "
            "background-color: white; border: 1px solid gray; padding: 2px;")
        self.date_label = QLabel("")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet(
            "font-size: 12px; font-family: Consolas, monospace; "
            "background-color: white; border: 1px solid gray; padding: 2px;")
        right_layout.addWidget(self.clock_label)
        right_layout.addWidget(self.date_label)

        right_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right_panel.setMinimumWidth(200)
        main_h.addWidget(right_panel, stretch=2)

        outer_v.addLayout(main_h, stretch=1)

        # --- Bottom panel ---
        bottom_panel = QFrame()
        bottom_panel.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        bottom_panel.setLineWidth(1)
        bp_bg = COLORS['bottom_panel_bg']
        bottom_panel.setStyleSheet(
            f"QFrame {{ background-color: rgb({bp_bg[0]},{bp_bg[1]},{bp_bg[2]}); }}")
        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(6, 4, 6, 4)
        bottom_layout.setSpacing(8)

        self.captured_widget = CapturedWidget()
        self.captured_widget.setStyleSheet("background: transparent;")
        self.captured_widget.set_board_widget(self.board_widget)
        bottom_layout.addWidget(self.captured_widget, stretch=1)

        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setStyleSheet(
            "color: rgb(0,255,0); font-size: 13px; "
            "font-style: italic; background: transparent;")
        bottom_layout.addWidget(self.message_label, stretch=1)

        self._bottom_panel = bottom_panel
        bottom_panel.setMinimumHeight(60)
        outer_v.addWidget(bottom_panel, stretch=0)

    # --- Connect controller signals ---

    def _connect_controller(self):
        """Wire controller signals to UI updates, and UI actions to controller."""
        c = self._controller

        # Controller → UI
        c.board_changed.connect(self._on_board_changed)
        c.turn_changed.connect(self._on_turn_changed)
        c.notation_added.connect(self._on_notation_added)
        c.game_over.connect(self._on_game_over)
        c.message_changed.connect(self._on_message_changed)
        c.captured_changed.connect(self._on_captured_changed)
        c.timer_tick.connect(self._on_timer_tick)
        c.ai_thinking.connect(self._on_ai_thinking)
        c.selection_changed.connect(self._on_selection_changed)
        c.capture_highlights_changed.connect(self._on_capture_highlights)

        # Board clicks → controller
        self.board_widget.cell_left_clicked.connect(c.on_cell_left_click)
        self.board_widget.cell_right_clicked.connect(c.on_cell_right_click)

        # Buttons → actions
        self.buttons["Отмена хода"].clicked.connect(self._on_undo)
        self.buttons["Открыть"].clicked.connect(self._on_load)
        self.buttons["Сохранить"].clicked.connect(self._on_save)
        self.buttons["Информация"].clicked.connect(self._on_info)
        self.buttons["Опции"].clicked.connect(self._on_options)
        self.buttons["Просмотр"].clicked.connect(self._on_playback)
        self.buttons["Развитие"].clicked.connect(self._on_development)
        self.buttons["Новая игра"].clicked.connect(self._on_new_game)
        self.buttons["Выход"].clicked.connect(self._on_exit)

        # Initial button states
        self.buttons["Отмена хода"].setEnabled(False)
        self.buttons["Сохранить"].setEnabled(False)

    # --- Controller signal handlers ---

    def _on_board_changed(self):
        self.board_widget.set_board(self._controller.board)
        self._update_button_states()

    def _on_turn_changed(self, color: str):
        self.highlight_turn(color)

    def _on_notation_added(self, move_text: str, color: str):
        if color == 'w':
            self.notation_white.append(move_text)
        else:
            self.notation_black.append(move_text)

    def _on_game_over(self, message: str):
        from draughts.ui.dialogs import GameOverDialog
        dlg = GameOverDialog(message, self)
        dlg.exec()
        if dlg.result_action == GameOverDialog.RESULT_PLAY_AGAIN:
            self._on_new_game()
        else:
            self.close()

    def _on_message_changed(self, text: str):
        self.message_label.setText(text)

    def _on_captured_changed(self, white_count: int, black_count: int):
        self.captured_widget.set_counts(white_count, black_count)

    def _on_timer_tick(self, seconds: int):
        mins = seconds // 60
        secs = seconds % 60
        self.timer_label.setText(f"{mins:02d}:{secs:02d}")

    def _on_ai_thinking(self, thinking: bool):
        # Disable board interaction while AI thinks
        self.board_widget.setEnabled(not thinking)
        for btn in self.buttons.values():
            btn.setEnabled(not thinking)

    def _on_selection_changed(self, x, y):
        if x is None:
            self.board_widget.set_selection()
        else:
            self.board_widget.set_selection(x, y)

    def _on_capture_highlights(self, positions: list):
        self.board_widget.set_capture_highlights(positions)

    # --- Button actions ---

    def _on_undo(self):
        self._controller.undo_move()

    def _on_load(self):
        from draughts.ui.dialogs import show_load_dialog
        filepath = show_load_dialog(self)
        if filepath:
            try:
                self._controller.load_saved_game(filepath)
                self.notation_white.clear()
                self.notation_black.clear()
                self.message_label.setText("Партия загружена")
            except Exception as e:
                self.message_label.setText(f"Ошибка загрузки: {e}")

    def _on_save(self):
        from draughts.ui.dialogs import show_save_dialog
        filepath = show_save_dialog(self)
        if filepath:
            try:
                self._controller.save_current_game(filepath)
                self.message_label.setText("Партия сохранена")
            except Exception as e:
                self.message_label.setText(f"Ошибка сохранения: {e}")

    def _on_info(self):
        from draughts.ui.dialogs import InfoDialog
        dlg = InfoDialog(self)
        dlg.exec()

    def _on_options(self):
        from draughts.ui.dialogs import OptionsDialog
        dlg = OptionsDialog(self._controller.settings, self)
        if dlg.exec():
            self._controller.settings = dlg.get_settings()
            self._controller._computer_color = (
                'b' if not self._controller.settings.invert_color else 'w')
            self._controller._player_color = (
                'w' if not self._controller.settings.invert_color else 'b')

    def _on_playback(self):
        from draughts.ui.playback import PlaybackDialog
        movie = self._controller.movie
        if len(movie) < 2:
            self.message_label.setText("Нет ходов для просмотра")
            return
        dlg = PlaybackDialog(movie, self)
        dlg.exec()

    def _on_development(self):
        from draughts.ui.dialogs import DevelopmentDialog
        dlg = DevelopmentDialog(self._controller.settings, self)
        if dlg.exec():
            dlg.apply_to(self._controller.settings)

    def _on_new_game(self):
        self.notation_white.clear()
        self.notation_black.clear()
        self._controller.new_game()

    def _on_exit(self):
        from draughts.ui.dialogs import ConfirmExitDialog
        dlg = ConfirmExitDialog(self)
        if dlg.exec():
            self.close()

    def _on_about(self):
        from draughts.ui.dialogs import AboutDialog
        dlg = AboutDialog(self)
        dlg.exec()

    # --- UI helpers ---

    def _update_button_states(self):
        self.buttons["Отмена хода"].setEnabled(self._controller.can_undo)
        self.buttons["Сохранить"].setEnabled(self._controller.can_save)

    def highlight_turn(self, color: str):
        if color == 'w':
            self.white_indicator.setStyleSheet(
                "background-color: white; color: black; "
                "border: 3px solid rgb(0,200,0); font-weight: bold; padding: 4px;")
            self.black_indicator.setStyleSheet(
                "background-color: black; color: white; "
                "border: 2px solid gray; font-weight: bold; padding: 4px;")
        else:
            self.white_indicator.setStyleSheet(
                "background-color: white; color: black; "
                "border: 2px solid gray; font-weight: bold; padding: 4px;")
            self.black_indicator.setStyleSheet(
                "background-color: black; color: white; "
                "border: 3px solid rgb(0,200,0); font-weight: bold; padding: 4px;")
        self.board_widget.set_turn_indicator(color)

    # --- Clock ---

    def _start_clock(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = datetime.now()
        self.clock_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(now.strftime("%d.%m.%Y"))

    # --- Resize event ---

    def resizeEvent(self, event):
        """Adjust bottom panel height proportionally to board cell size."""
        super().resizeEvent(event)
        # Original 640x480: cell=40px, bottom panel=95px ≈ 2.4 cells
        cell_size = self.board_widget.get_cell_size()
        panel_h = max(60, int(cell_size * 2.4))
        # Cap at 20% of window height to prevent squishing the board
        max_h = int(self.height() * 0.20)
        panel_h = min(panel_h, max_h)
        self._bottom_panel.setFixedHeight(panel_h)

    # --- Close event ---

    def closeEvent(self, event):
        # Save learning DB on exit
        try:
            self._controller.learning_db.save()
        except Exception:
            pass
        event.accept()
