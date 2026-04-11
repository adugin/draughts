"""Main window for the Draughts application.

Minimal layout: menu bar + board widget only.
All controls accessible via standard menus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from draughts.config import Color
from draughts.ui.board_widget import BoardWidget

if TYPE_CHECKING:
    from draughts.game.controller import GameController


class MainWindow(QMainWindow):
    """Main application window — board + menu bar."""

    def __init__(self, controller: GameController, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Шашки")
        self.setMinimumSize(480, 520)
        self.resize(720, 760)

        self._controller = controller

        self._build_ui()
        self._build_menus()
        self._connect_controller()

    def _build_ui(self):
        """Board widget as the sole central content."""
        central = QWidget()
        central.setStyleSheet("background-color: #2a1a0a;")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.board_widget = BoardWidget()
        self.board_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.board_widget)

        # No status bar
        self.setStatusBar(None)

    def _build_menus(self):
        """Create standard menu bar with all game actions."""
        menubar = self.menuBar()

        # --- Игра ---
        game_menu = menubar.addMenu("&Игра")

        self._act_new = QAction("&Новая игра", self)
        self._act_new.setShortcut(QKeySequence("Ctrl+N"))
        self._act_new.triggered.connect(self._on_new_game)
        game_menu.addAction(self._act_new)

        game_menu.addSeparator()

        self._act_load = QAction("&Открыть...", self)
        self._act_load.setShortcut(QKeySequence("Ctrl+O"))
        self._act_load.triggered.connect(self._on_load)
        game_menu.addAction(self._act_load)

        self._act_save = QAction("&Сохранить...", self)
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        self._act_save.setEnabled(False)
        self._act_save.triggered.connect(self._on_save)
        game_menu.addAction(self._act_save)

        game_menu.addSeparator()

        self._act_undo = QAction("О&тмена хода", self)
        self._act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self._act_undo.setEnabled(False)
        self._act_undo.triggered.connect(self._on_undo)
        game_menu.addAction(self._act_undo)

        game_menu.addSeparator()

        self._act_exit = QAction("Вы&ход", self)
        self._act_exit.setShortcut(QKeySequence("Alt+F4"))
        self._act_exit.triggered.connect(self._on_exit)
        game_menu.addAction(self._act_exit)

        # --- Настройки ---
        settings_menu = menubar.addMenu("&Настройки")

        self._act_options = QAction("&Опции...", self)
        self._act_options.setShortcut(QKeySequence("Ctrl+P"))
        self._act_options.triggered.connect(self._on_options)
        settings_menu.addAction(self._act_options)

        # --- Вид ---
        view_menu = menubar.addMenu("&Вид")

        self._act_playback = QAction("&Просмотр партии...", self)
        self._act_playback.setShortcut(QKeySequence("Ctrl+R"))
        self._act_playback.triggered.connect(self._on_playback)
        view_menu.addAction(self._act_playback)

        # --- Справка ---
        help_menu = menubar.addMenu("&Справка")

        self._act_info = QAction("&Информация...", self)
        self._act_info.setShortcut(QKeySequence("F1"))
        self._act_info.triggered.connect(self._on_info)
        help_menu.addAction(self._act_info)

        self._act_about = QAction("&Об авторе...", self)
        self._act_about.triggered.connect(self._on_about)
        help_menu.addAction(self._act_about)

    # --- Connect controller signals ---

    def _connect_controller(self):
        """Wire controller signals to UI updates, and UI actions to controller."""
        c = self._controller

        c.board_changed.connect(self._on_board_changed)
        c.turn_changed.connect(self._on_turn_changed)
        c.game_over.connect(self._on_game_over)
        c.ai_thinking.connect(self._on_ai_thinking)
        c.selection_changed.connect(self._on_selection_changed)
        c.capture_highlights_changed.connect(self._on_capture_highlights)
        c.capture_hint.connect(self._on_capture_hint)

        # Board clicks → controller
        self.board_widget.cell_left_clicked.connect(c.on_cell_left_click)
        self.board_widget.cell_right_clicked.connect(c.on_cell_right_click)

    # --- Controller signal handlers ---

    def _on_board_changed(self):
        self.board_widget.set_board(self._controller.board)
        self._update_action_states()

    def _on_turn_changed(self, color: str):
        self.board_widget.set_turn_indicator(color)

    def _on_game_over(self, message: str):
        from draughts.ui.dialogs import GameOverDialog

        dlg = GameOverDialog(message, self)
        dlg.exec()
        if dlg.result_action == GameOverDialog.RESULT_PLAY_AGAIN:
            self._on_new_game()
        else:
            self.close()

    def _on_ai_thinking(self, thinking: bool):
        self.board_widget.setEnabled(not thinking)
        self._act_undo.setEnabled(not thinking and self._controller.can_undo)
        self._act_save.setEnabled(not thinking and self._controller.can_save)
        self._act_new.setEnabled(not thinking)
        self._act_load.setEnabled(not thinking)

    def _on_selection_changed(self, x, y):
        if x is None:
            self.board_widget.set_selection()
        else:
            self.board_widget.set_selection(x, y)

    def _on_capture_highlights(self, positions: list):
        self.board_widget.set_capture_highlights(positions)

    def _on_capture_hint(self, positions: list):
        self.board_widget.start_hint_pulse(positions)

    # --- Menu actions ---

    def _on_undo(self):
        self._controller.undo_move()

    def _on_load(self):
        from draughts.ui.dialogs import show_load_dialog

        filepath = show_load_dialog(self)
        if filepath:
            try:
                self._controller.load_saved_game(filepath)
            except Exception:
                pass

    def _on_save(self):
        from draughts.ui.dialogs import show_save_dialog

        filepath = show_save_dialog(self)
        if filepath:
            try:
                self._controller.save_current_game(filepath)
            except Exception:
                pass

    def _on_info(self):
        from draughts.ui.dialogs import InfoDialog

        dlg = InfoDialog(self)
        dlg.exec()

    def _on_options(self):
        from draughts.ui.dialogs import OptionsDialog

        dlg = OptionsDialog(self._controller.settings, self)
        if dlg.exec():
            self._controller.settings = dlg.get_settings()
            self._controller._computer_color = Color.BLACK if not self._controller.settings.invert_color else Color.WHITE
            self._controller._player_color = Color.WHITE if not self._controller.settings.invert_color else Color.BLACK

    def _on_playback(self):
        from draughts.ui.playback import PlaybackDialog

        replay = self._controller.replay_history
        if len(replay) < 2:
            return
        dlg = PlaybackDialog(replay, self)
        dlg.exec()

    def _on_new_game(self):
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

    def _update_action_states(self):
        self._act_undo.setEnabled(self._controller.can_undo)
        self._act_save.setEnabled(self._controller.can_save)

    # --- Close event ---

    def closeEvent(self, event):
        event.accept()
