"""Main window for the Draughts application."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from draughts.config import BTN_LABELS, COLORS
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
        self.resize(1024, 720)

        self._controller = controller

        self._build_ui()
        self._start_clock()
        self._connect_controller()

    def _build_ui(self):
        """Construct the complete UI layout."""
        central = QWidget()
        central.setStyleSheet("background-color: #2a1a0a;")
        self.setCentralWidget(central)

        outer_v = QVBoxLayout(central)
        outer_v.setContentsMargins(4, 4, 4, 4)
        outer_v.setSpacing(4)

        # Header label
        self.header_label = QLabel("Автор и разработчик программы: Андрей Дугин")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_label.setStyleSheet(
            "background-color: #2a1a0a; color: #c8a87a; "
            "font-weight: bold; padding: 4px; "
            "border: 1px solid #5a3a1a; font-size: 12px;"
        )
        self.header_label.setFixedHeight(28)
        self.header_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_label.mousePressEvent = lambda e: self._on_about()
        outer_v.addWidget(self.header_label)

        # Main area: board + right panel
        main_h = QHBoxLayout()
        main_h.setSpacing(0)

        # --- Board widget ---
        self.board_widget = BoardWidget()
        self.board_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_h.addWidget(self.board_widget, stretch=3)

        # --- Right area: notation columns + buttons column (like original) ---
        right_panel = QFrame()
        right_panel.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        right_panel.setLineWidth(1)
        right_panel.setStyleSheet(
            "QFrame { background-color: #3a2a1a; border: 1px solid #5a3a1a; }")

        right_h = QHBoxLayout(right_panel)
        right_h.setContentsMargins(6, 6, 6, 6)
        right_h.setSpacing(4)

        # -- Left sub-column: indicators + notation --
        notation_col = QVBoxLayout()
        notation_col.setSpacing(4)

        # Turn indicators with piece symbols
        turn_row = QHBoxLayout()
        self.white_indicator = QLabel("  Белые  ")
        self.white_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.white_indicator.setStyleSheet(
            "background-color: #f0e6d0; color: #2a1a0a; "
            "border: 2px solid #8a7a5a; font-weight: bold; padding: 4px; border-radius: 3px;")
        self.black_indicator = QLabel("  Чёрные  ")
        self.black_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.black_indicator.setStyleSheet(
            "background-color: #1a1210; color: #c8a87a; "
            "border: 2px solid #5a4a3a; font-weight: bold; padding: 4px; border-radius: 3px;")
        turn_row.addWidget(self.white_indicator)
        turn_row.addWidget(self.black_indicator)
        notation_col.addLayout(turn_row)

        # Two notation columns side by side
        notation_row = QHBoxLayout()
        self.notation_white = QTextEdit()
        self.notation_white.setReadOnly(True)
        self.notation_white.setPlaceholderText("Белые")
        self.notation_white.setStyleSheet(
            "background-color: #f5ead0; color: #2a1a0a; "
            "font-family: Consolas, monospace; border: 1px solid #8a7a5a; border-radius: 2px;")

        self.notation_black = QTextEdit()
        self.notation_black.setReadOnly(True)
        self.notation_black.setPlaceholderText("Чёрные")
        self.notation_black.setStyleSheet(
            "background-color: #1a1210; color: #c8a87a; "
            "font-family: Consolas, monospace; border: 1px solid #5a4a3a; border-radius: 2px;")

        notation_row.addWidget(self.notation_white)
        notation_row.addWidget(self.notation_black)
        notation_col.addLayout(notation_row, stretch=1)

        right_h.addLayout(notation_col, stretch=1)

        # -- Right sub-column: buttons + timer/clock --
        btn_style = (
            "QPushButton { background-color: #4a3520; color: #e8d8b8; "
            "border: 1px solid #6a4a2a; padding: 3px 8px; "
            "border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background-color: #5a4530; "
            "border-color: #8a6a4a; }"
            "QPushButton:pressed { background-color: #3a2510; }"
            "QPushButton:disabled { color: #6a5a4a; background-color: #3a2a1a; }"
        )

        buttons_col = QVBoxLayout()
        buttons_col.setSpacing(3)

        self.buttons: dict[str, QPushButton] = {}
        for label in BTN_LABELS:
            btn = QPushButton(label)
            btn.setMinimumHeight(26)
            btn.setStyleSheet(btn_style)
            self.buttons[label] = btn
            buttons_col.addWidget(btn)

        buttons_col.addStretch()

        # Timer
        self.timer_label = QLabel("00:30")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; "
            "font-family: Consolas, monospace; "
            "background-color: #1a1210; color: #d0b080; "
            "border: 1px solid #5a4a3a; padding: 4px; border-radius: 3px;")
        buttons_col.addWidget(self.timer_label)

        # Clock and date
        self.clock_label = QLabel("00:00:00")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet(
            "font-size: 13px; font-family: Consolas, monospace; "
            "background-color: #1a1210; color: #a09070; "
            "border: 1px solid #5a4a3a; padding: 2px; border-radius: 2px;")
        self.date_label = QLabel("")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet(
            "font-size: 11px; font-family: Consolas, monospace; "
            "background-color: #1a1210; color: #a09070; "
            "border: 1px solid #5a4a3a; padding: 2px; border-radius: 2px;")
        buttons_col.addWidget(self.clock_label)
        buttons_col.addWidget(self.date_label)

        right_h.addLayout(buttons_col)

        right_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right_panel.setMinimumWidth(280)
        main_h.addWidget(right_panel, stretch=2)

        outer_v.addLayout(main_h, stretch=1)

        # --- Bottom panel (green felt — single unified background) ---
        bottom_panel = QFrame()
        bottom_panel.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        bottom_panel.setLineWidth(1)
        bottom_panel.setStyleSheet(
            "QFrame { border: 1px solid #1a4a1a; }")

        # CapturedWidget fills the entire bottom panel and draws felt background
        self.captured_widget = CapturedWidget()
        self.captured_widget.set_board_widget(self.board_widget)

        # Message label overlaid on top — absolutely positioned via stacked layout
        self.message_label = QLabel("")
        self.message_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.message_label.setStyleSheet(
            "color: #80d080; font-size: 13px; "
            "font-style: italic; background: transparent; padding-right: 16px;")

        # Use a simple layout — captured widget takes all space, message on top via overlay
        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        bottom_layout.addWidget(self.captured_widget)

        # Overlay message_label on the right side of captured widget
        self.message_label.setParent(self.captured_widget)

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
        replay = self._controller.replay_history
        if len(replay) < 2:
            self.message_label.setText("Нет ходов для просмотра")
            return
        dlg = PlaybackDialog(replay, self)
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
        active_border = "border: 3px solid #c8a040;"
        inactive_border = "border: 2px solid #5a4a3a;"
        if color == 'w':
            self.white_indicator.setStyleSheet(
                f"background-color: #f0e6d0; color: #2a1a0a; "
                f"{active_border} font-weight: bold; padding: 4px; border-radius: 3px;")
            self.black_indicator.setStyleSheet(
                f"background-color: #1a1210; color: #c8a87a; "
                f"{inactive_border} font-weight: bold; padding: 4px; border-radius: 3px;")
        else:
            self.white_indicator.setStyleSheet(
                f"background-color: #f0e6d0; color: #2a1a0a; "
                f"{inactive_border} font-weight: bold; padding: 4px; border-radius: 3px;")
            self.black_indicator.setStyleSheet(
                f"background-color: #1a1210; color: #c8a87a; "
                f"{active_border} font-weight: bold; padding: 4px; border-radius: 3px;")
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
        """Adjust bottom panel height and message label position."""
        super().resizeEvent(event)
        cell_size = self.board_widget.get_cell_size()
        panel_h = max(60, int(cell_size * 2.4))
        max_h = int(self.height() * 0.20)
        panel_h = min(panel_h, max_h)
        self._bottom_panel.setFixedHeight(panel_h)

        # Position message label on the right half of captured widget
        cw = self.captured_widget
        w = cw.width()
        h = cw.height()
        self.message_label.setGeometry(w // 2, 0, w // 2, h)

    # --- Close event ---

    def closeEvent(self, event):
        # Save learning DB on exit
        try:
            self._controller.learning_db.save()
        except Exception:
            pass
        event.accept()
