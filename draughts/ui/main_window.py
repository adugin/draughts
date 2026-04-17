"""Main window for the Draughts application.

Minimal layout: menu bar + board widget only.
All controls accessible via standard menus.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger("draughts.main_window")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QButtonGroup,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from draughts.config import APP_NAME, BOARD_PX, BOARD_SIZE, Color
from draughts.ui.analysis_pane import AnalysisPane
from draughts.ui.board_widget import BoardWidget
from draughts.ui.theme_engine import apply_theme as _apply_engine_theme
from draughts.ui.theme_engine import get_theme_colors

if TYPE_CHECKING:
    from draughts.app.controller import GameController


class MainWindow(QMainWindow):
    """Main application window — board + menu bar."""

    def __init__(self, controller: GameController, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        # Window size is built FROM the board, not the other way around.
        # Board widget gets a fixed square size; the window wraps tightly.
        # setFixedSize is called AFTER _build_ui so the layout can compute.

        self._controller = controller
        self._current_theme = controller.settings.board_theme

        self._build_ui()
        self._build_menus()
        self._build_analysis_pane()
        self._connect_controller()
        self._apply_theme(self._current_theme)

        # Lock window size: board dictates width, layout adds menu/toolbar.
        self.adjustSize()
        self.setFixedSize(self.size())

    def _apply_theme(self, theme_name: str) -> None:
        """Apply the themed stylesheet to the entire window."""
        self._current_theme = theme_name
        _apply_engine_theme(self, theme_name)
        # Refresh analysis pane inline styles (UX-001)
        if hasattr(self, "_analysis_pane"):
            self._analysis_pane.refresh_theme(theme_name)

    def _build_ui(self):
        """Board widget as the sole central content."""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.board_widget = BoardWidget()
        self.board_widget.setFixedSize(BOARD_PX, BOARD_PX)
        layout.addWidget(self.board_widget, alignment=Qt.AlignmentFlag.AlignCenter)

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
        self._act_save.triggered.connect(self._on_save)
        game_menu.addAction(self._act_save)

        game_menu.addSeparator()

        self._act_undo = QAction("О&тмена хода", self)
        self._act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self._act_undo.triggered.connect(self._on_undo)
        game_menu.addAction(self._act_undo)

        self._act_hint = QAction("&Подсказка", self)
        self._act_hint.setShortcut(QKeySequence("Ctrl+H"))
        self._act_hint.triggered.connect(self._on_hint)
        game_menu.addAction(self._act_hint)

        self._act_flip = QAction("&Сменить сторону", self)
        self._act_flip.setShortcut(QKeySequence("Ctrl+F"))
        self._act_flip.triggered.connect(self._on_flip_sides)
        game_menu.addAction(self._act_flip)

        self._act_resign = QAction("С&даться", self)
        self._act_resign.triggered.connect(self._on_resign)
        game_menu.addAction(self._act_resign)

        game_menu.addSeparator()

        self._act_exit = QAction("Вы&ход", self)
        self._act_exit.setShortcut(QKeySequence("Alt+F4"))
        self._act_exit.triggered.connect(self._on_exit)
        game_menu.addAction(self._act_exit)

        # --- Настройки ---
        settings_menu = menubar.addMenu("&Настройки")

        self._act_options = QAction("&Опции...", self)
        self._act_options.setShortcut(QKeySequence("Ctrl+,"))
        self._act_options.triggered.connect(self._on_options)
        settings_menu.addAction(self._act_options)

        # --- Тренировка ---
        training_menu = menubar.addMenu("&Тренировка")

        self._act_puzzles = QAction("Решать &задачи...", self)
        self._act_puzzles.setShortcut(QKeySequence("Ctrl+P"))
        self._act_puzzles.triggered.connect(self._on_puzzles)
        training_menu.addAction(self._act_puzzles)

        # --- Вид ---
        view_menu = menubar.addMenu("&Вид")

        self._act_playback = QAction("&Просмотр партии...", self)
        self._act_playback.setShortcut(QKeySequence("Ctrl+R"))
        self._act_playback.triggered.connect(self._on_playback)
        view_menu.addAction(self._act_playback)

        # --- Позиция ---
        position_menu = menubar.addMenu("По&зиция")

        self._act_editor = QAction("&Редактор...", self)
        self._act_editor.setShortcut(QKeySequence("Ctrl+E"))
        self._act_editor.triggered.connect(self.enter_editor_mode)
        position_menu.addAction(self._act_editor)

        position_menu.addSeparator()

        self._act_copy_fen = QAction("&Копировать FEN", self)
        self._act_copy_fen.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self._act_copy_fen.triggered.connect(self._on_copy_fen)
        position_menu.addAction(self._act_copy_fen)

        self._act_paste_fen = QAction("&Вставить FEN", self)
        self._act_paste_fen.setShortcut(QKeySequence("Ctrl+Shift+V"))
        self._act_paste_fen.triggered.connect(self._on_paste_fen)
        position_menu.addAction(self._act_paste_fen)

        # --- Анализ ---
        analysis_menu = menubar.addMenu("&Анализ")

        self._act_toggle_pane = QAction("&Панель анализа", self)
        self._act_toggle_pane.setShortcut(QKeySequence("F3"))
        self._act_toggle_pane.setCheckable(True)
        self._act_toggle_pane.setChecked(False)
        self._act_toggle_pane.triggered.connect(self._on_toggle_analysis_pane)
        analysis_menu.addAction(self._act_toggle_pane)

        analysis_menu.addSeparator()

        self._act_analyze_game = QAction("&Проанализировать партию...", self)
        self._act_analyze_game.triggered.connect(self._on_analyze_game)
        analysis_menu.addAction(self._act_analyze_game)

        # --- Справка ---
        help_menu = menubar.addMenu("&Справка")

        self._act_info = QAction("&Информация...", self)
        self._act_info.setShortcut(QKeySequence("F1"))
        self._act_info.triggered.connect(self._on_info)
        help_menu.addAction(self._act_info)

        self._act_about = QAction("&Об авторе...", self)
        self._act_about.triggered.connect(self._on_about)
        help_menu.addAction(self._act_about)

    def _build_analysis_pane(self) -> None:
        """Create the analysis dock pane (initially hidden)."""
        self._analysis_pane = AnalysisPane(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._analysis_pane)
        self._analysis_pane.hide()
        # Keep the menu checkbox in sync when user closes the dock with the X button
        self._analysis_pane.visibilityChanged.connect(self._on_pane_visibility_changed)

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
        c.last_move_changed.connect(self._on_last_move_changed)
        c.hint_ready.connect(self._on_hint_ready)
        c.message_changed.connect(self._on_message_changed)

        # Push initial settings to board widget
        self.board_widget.set_settings(c.settings)
        self.board_widget.set_theme(getattr(c.settings, "board_theme", "dark_wood"))
        self.board_widget.inverted = c.settings.invert_color

        # Board clicks → controller
        self.board_widget.cell_left_clicked.connect(c.on_cell_left_click)
        self.board_widget.cell_right_clicked.connect(c.on_cell_right_click)

    # --- Controller signal handlers ---

    def _on_board_changed(self):
        self.board_widget.set_board(self._controller.board)
        self._update_action_states()
        # Auto-feed new position to analysis pane (only when pane is visible
        # and engine is not already thinking for the game).
        if self._analysis_pane.isVisible() and not self._controller.is_thinking:
            self._analysis_pane.set_position(self._controller.board, self._controller.current_turn)

    def _on_turn_changed(self, color: str):
        self.board_widget.set_turn_indicator(color)
        # Flip-sides availability depends on whose turn it is (D36).
        self._update_action_states()

    def _on_game_over(self, message: str):
        from draughts.ui.dialogs import GameOverDialog

        dlg = GameOverDialog(message, self, theme=self._current_theme)
        dlg.exec()
        if dlg.result_action == GameOverDialog.RESULT_PLAY_AGAIN:
            self._on_new_game()
        else:
            self.close()

    def _on_ai_thinking(self, thinking: bool):
        self.board_widget.setEnabled(not thinking)
        self._update_action_states()
        # Wait cursor while AI is thinking
        if thinking:
            self.setCursor(Qt.CursorShape.WaitCursor)
        else:
            self.unsetCursor()

    def _on_selection_changed(self, x, y):
        if x is None:
            self.board_widget.set_selection()
        else:
            self.board_widget.set_selection(x, y)

    def _on_capture_highlights(self, positions: list):
        self.board_widget.set_capture_highlights(positions)

    def _on_capture_hint(self, positions: list):
        self.board_widget.start_hint_pulse(positions)

    def _on_last_move_changed(self, move):
        """Propagate last-move highlight to board widget."""
        self.board_widget.last_move = move

    def _on_hint_ready(self, squares: list, message: str):
        """Display the hint squares on the board and show a status message (D16)."""
        self.board_widget.hint_squares = squares
        # Show as a transient message box in the title bar area
        self.setWindowTitle(f"{APP_NAME} — {message}")
        # Restore plain title after 4 seconds
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(4000, lambda: self.setWindowTitle(APP_NAME))

    def _on_message_changed(self, message: str):
        """Show controller messages (thinking, mandatory capture hints) in title bar."""
        if message:
            self.setWindowTitle(f"{APP_NAME} — {message}")
        else:
            self.setWindowTitle(APP_NAME)

    # --- Menu actions ---

    def _on_undo(self):
        self._controller.undo_move()

    def _on_load(self):
        from draughts.ui.dialogs import show_load_dialog

        filepath = show_load_dialog(self)
        if filepath:
            try:
                if filepath.lower().endswith(".pdn"):
                    self._controller.load_game_from_pdn(filepath)
                else:
                    self._controller.load_saved_game(filepath)
                # Sync board orientation with the loaded invert_color flag —
                # load_saved_game mutates settings but doesn't signal the UI.
                self.board_widget.inverted = self._controller.settings.invert_color
            except Exception:
                logger.exception("Failed to load game from %s", filepath)

    def _on_save(self):
        from draughts.ui.dialogs import show_save_dialog

        filepath = show_save_dialog(self)
        if filepath:
            try:
                if filepath.lower().endswith(".pdn"):
                    self._controller.save_game_as_pdn(filepath)
                else:
                    self._controller.save_current_game(filepath)
            except Exception:
                logger.exception("Failed to save game to %s", filepath)

    def _on_info(self):
        from draughts.ui.dialogs import InfoDialog

        dlg = InfoDialog(self, theme=self._current_theme)
        dlg.exec()

    def _on_hint(self):
        """Request a hint from the engine (D16, Ctrl+H)."""
        self._controller.get_hint()

    def _on_flip_sides(self):
        """Swap sides mid-game and flip the board so the player is at bottom (Ctrl+F)."""
        if self.board_widget.editor_mode:
            return
        self._controller.flip_sides()
        self.board_widget.inverted = (self._controller.player_color == Color.BLACK)
        # Clear any stale hint/hover overlays — they belonged to the
        # former player (BUG-8).
        self.board_widget.hint_squares = None
        self.board_widget._hover_legal_moves = []

    def _on_resign(self):
        """Player resigns — ask for confirmation, then end the game."""
        if self.board_widget.editor_mode:
            return
        reply = QMessageBox.question(
            self,
            "Сдаться",
            "Вы уверены, что хотите сдаться?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._controller.resign()

    def _on_options(self):
        from draughts.ui.dialogs import OptionsDialog

        dlg = OptionsDialog(self._controller.settings, self)
        if dlg.exec():
            old_invert = self._controller.settings.invert_color
            self._controller.settings = dlg.get_settings()
            new_invert = self._controller.settings.invert_color
            self._controller._computer_color = (
                Color.BLACK if not new_invert else Color.WHITE
            )
            self._controller._player_color = Color.WHITE if not new_invert else Color.BLACK
            # Propagate updated settings to board widget (coordinates, hover, etc.)
            self.board_widget.set_settings(self._controller.settings)
            # Apply theme change to board AND entire window (D18)
            new_theme = getattr(self._controller.settings, "board_theme", "dark_wood")
            if new_theme != self._current_theme:
                self.board_widget.set_theme(new_theme)
                self._apply_theme(new_theme)
            # Apply board orientation (D22)
            self.board_widget.inverted = self._controller.settings.invert_color
            # Apply tuned eval toggle immediately (BUG-004)
            from draughts.game.ai.eval import set_use_tuned_eval

            set_use_tuned_eval(self._controller.settings.use_tuned_eval)

            # Persist user preferences to disk
            from draughts.config import save_settings
            save_settings(self._controller.settings)

            # If player switched sides, start a new game so the
            # computer moves first when it's now white.
            if old_invert != new_invert:
                self._controller.new_game()

    def _on_copy_fen(self):
        """Copy current board position as FEN to clipboard (D36)."""
        from PyQt6.QtWidgets import QApplication

        from draughts.game.fen import board_to_fen

        board = self._controller.board
        color = self._controller.current_turn
        fen = board_to_fen(board, color)
        QApplication.clipboard().setText(fen)
        self.setWindowTitle(f"{APP_NAME} — FEN скопирован")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self.setWindowTitle(APP_NAME))

    def _on_paste_fen(self):
        """Paste FEN from clipboard and start a new game from it (D36)."""
        from PyQt6.QtWidgets import QApplication

        from draughts.game.fen import parse_fen

        text = QApplication.clipboard().text()
        if not text or not text.strip():
            QMessageBox.warning(self, "Вставить FEN", "Буфер обмена пуст.")
            return
        try:
            board, color = parse_fen(text.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка FEN", f"Неверный FEN:\n{exc}")
            return
        self._controller.new_game_from_position(board, color)

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

        dlg = ConfirmExitDialog(self, theme=self._current_theme)
        if dlg.exec():
            self.close()

    def _on_about(self):
        from draughts.ui.dialogs import AboutDialog

        dlg = AboutDialog(self, theme=self._current_theme)
        dlg.exec()

    def _on_puzzles(self):
        from draughts.ui.puzzle_widget import PuzzleTrainer

        dlg = PuzzleTrainer(self)
        dlg.exec()

    def _on_toggle_analysis_pane(self, checked: bool) -> None:
        """Show or hide the analysis pane."""
        if checked:
            self._pane_saved_size = self.size()
            # Unlock size so the dock can expand the window
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self._analysis_pane.show()
            # Prime the pane with the current position
            if not self._controller.is_thinking:
                self._analysis_pane.set_position(self._controller.board, self._controller.current_turn)
        else:
            self._analysis_pane.stop_analysis()
            self._analysis_pane.hide()
            # Restore exact window size — no timer, no flicker
            if hasattr(self, "_pane_saved_size"):
                self.setFixedSize(self._pane_saved_size)

    def _on_pane_visibility_changed(self, visible: bool) -> None:
        """Keep the menu checkbox synced with the dock widget's actual visibility."""
        self._act_toggle_pane.setChecked(visible)
        if not visible and hasattr(self, "_pane_saved_size"):
            self.setFixedSize(self._pane_saved_size)

    def _on_analyze_game(self) -> None:
        """Run full-game analysis and show annotations + summary."""
        from draughts.ui.game_analyzer import run_game_analysis

        run_game_analysis(self._controller, self)

    # --- Board editor ---

    def enter_editor_mode(self):
        """Enter board editor mode: save state, disable game logic, show toolbar."""
        if self.board_widget.editor_mode:
            return  # already in editor mode

        # Snapshot the current game state for Cancel
        self._editor_saved_positions = list(self._controller._positions)
        self._editor_saved_replay = list(self._controller._replay_history)
        self._editor_saved_ply = self._controller._ply_count
        self._editor_saved_turn = self._controller._current_turn
        self._editor_saved_player_color = self._controller._player_color
        self._editor_saved_board = self._controller.board.copy()
        self._editor_saved_position_counts = dict(self._controller._position_counts)

        # Invalidate any running AI (BUG-3): do NOT block main thread with
        # quit()+wait() — AI.find_move() is a tight Python loop that doesn't
        # check Qt's quit flag, so wait() would freeze the UI for seconds.
        # Instead bump the generation token (same mechanism as flip_sides);
        # the stale worker's result is dropped when it finishes, and the
        # thread self-cleans via the finished-handler's stale path.
        if self._controller._ai_thread is not None:
            self._controller._ai_generation += 1
            if self._controller._ai_worker is not None:
                self._controller._pending_ai.append(
                    (self._controller._ai_thread, self._controller._ai_worker)
                )
            self._controller._ai_thread = None
            self._controller._ai_worker = None
            self._controller.ai_thinking.emit(False)

        # Make a working copy of the board for editing
        self._editor_board = self._controller.board.copy()
        self.board_widget.set_board(self._editor_board)
        self.board_widget.set_selection()
        self.board_widget.set_capture_highlights([])

        # Default side-to-move in the editor
        self._editor_turn = self._controller._current_turn

        # Enable editor mode on the widget
        self.board_widget.editor_mode = True

        # Save window size before adding toolbars
        self._editor_saved_size = self.size()

        # Unlock window size so toolbars can expand it
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)

        # Build editor toolbars at the bottom (like analysis pane)
        _tc = get_theme_colors(self._current_theme)

        # --- Row 1: Play / Analyze / Cancel + side-to-move ---
        self._editor_toolbar = QToolBar("Редактор", self)
        self._editor_toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self._editor_toolbar)

        btn_play = QPushButton("▶ Играть")
        btn_play.setToolTip("Начать игру из этой позиции")
        btn_play.setStyleSheet(f"font-weight: bold; color: {_tc['editor_play_fg']};")
        btn_play.clicked.connect(self._editor_play_from_here)
        self._editor_toolbar.addWidget(btn_play)

        btn_analyze = QPushButton("Анализ")
        btn_analyze.setToolTip("Анализировать эту позицию")
        btn_analyze.clicked.connect(self._editor_analyze_from_here)
        self._editor_toolbar.addWidget(btn_analyze)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setToolTip("Отмена (Escape)")
        btn_cancel.setStyleSheet(f"color: {_tc['editor_cancel_fg']};")
        btn_cancel.clicked.connect(self._editor_cancel)
        self._editor_toolbar.addWidget(btn_cancel)

        self._editor_toolbar.addSeparator()

        # Side-to-move (whose turn after pressing Play)
        lbl = QLabel("  Чей ход:")
        lbl.setStyleSheet(f"color: {_tc['fg']}; padding: 0 2px;")
        self._editor_toolbar.addWidget(lbl)

        self._editor_radio_white = QRadioButton("Белых")
        self._editor_radio_black = QRadioButton("Чёрных")

        self._editor_side_group = QButtonGroup(self)
        self._editor_side_group.addButton(self._editor_radio_white)
        self._editor_side_group.addButton(self._editor_radio_black)

        if self._editor_turn == Color.WHITE:
            self._editor_radio_white.setChecked(True)
        else:
            self._editor_radio_black.setChecked(True)

        self._editor_toolbar.addWidget(self._editor_radio_white)
        self._editor_toolbar.addWidget(self._editor_radio_black)

        # --- Row 2: tools (clear, reset, FEN) ---
        self._editor_toolbar2 = QToolBar("Инструменты", self)
        self._editor_toolbar2.setMovable(False)
        self.addToolBarBreak(Qt.ToolBarArea.BottomToolBarArea)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self._editor_toolbar2)

        btn_clear = QPushButton("Очистить доску")
        btn_clear.clicked.connect(self._editor_clear_board)
        self._editor_toolbar2.addWidget(btn_clear)

        btn_start = QPushButton("Начальная позиция")
        btn_start.clicked.connect(self._editor_start_position)
        self._editor_toolbar2.addWidget(btn_start)

        self._editor_toolbar2.addSeparator()

        btn_import = QPushButton("Импорт FEN")
        btn_import.setToolTip("Вставить позицию из буфера обмена")
        btn_import.clicked.connect(self._editor_import_fen)
        self._editor_toolbar2.addWidget(btn_import)

        btn_export = QPushButton("Экспорт FEN")
        btn_export.setToolTip("Скопировать позицию в буфер обмена")
        btn_export.clicked.connect(self._editor_export_fen)
        self._editor_toolbar2.addWidget(btn_export)

        self._update_action_states()

    def exit_editor_mode(self):
        """Exit editor mode and remove the toolbar."""
        if not self.board_widget.editor_mode:
            return
        self.board_widget.editor_mode = False
        for attr in ("_editor_toolbar", "_editor_toolbar2"):
            tb = getattr(self, attr, None)
            if tb is not None:
                self.removeToolBar(tb)
                tb.deleteLater()
                setattr(self, attr, None)
        self._update_action_states()
        # Restore exact window size — no adjustSize() delay, no flicker
        if hasattr(self, "_editor_saved_size"):
            self.setFixedSize(self._editor_saved_size)

    def _editor_side(self) -> Color:
        """Return the currently selected side-to-move from the editor toolbar."""
        if hasattr(self, "_editor_radio_black") and self._editor_radio_black.isChecked():
            return Color.BLACK
        return Color.WHITE

    def _editor_clear_board(self):
        """Clear all pieces from the editor board."""
        from draughts.game.board import Board

        self._editor_board = Board(empty=True)
        self.board_widget.set_board(self._editor_board)

    def _editor_start_position(self):
        """Reset editor board to the standard starting position."""
        from draughts.game.board import Board

        self._editor_board = Board()
        self.board_widget.set_board(self._editor_board)

    def _editor_export_fen(self):
        """Export the current editor position as a FEN string, copy to clipboard."""
        from PyQt6.QtWidgets import QApplication

        from draughts.game.fen import board_to_fen

        fen = board_to_fen(self._editor_board, self._editor_side())
        QApplication.clipboard().setText(fen)
        QMessageBox.information(
            self,
            "Экспорт FEN",
            f"FEN скопирован в буфер обмена:\n\n{fen}",
        )

    def _editor_import_fen(self):
        """Import a FEN string into the editor board."""
        from draughts.game.fen import parse_fen

        text, ok = QInputDialog.getText(
            self,
            "Импорт FEN",
            "Введите FEN-строку:",
        )
        if not ok or not text.strip():
            return
        try:
            board, color = parse_fen(text.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка FEN", f"Неверный FEN:\n{exc}")
            return
        self._editor_board = board
        self.board_widget.set_board(self._editor_board)
        if color == Color.WHITE:
            self._editor_radio_white.setChecked(True)
        else:
            self._editor_radio_black.setChecked(True)

    def _editor_validate_and_fix(self) -> Board | None:
        """Validate the editor board, auto-fix pawns on promotion rows.

        Returns a fixed copy of the board, or None if the position is
        invalid (shows an error dialog).
        """
        import numpy as np

        board = self._editor_board.copy()
        grid = board.grid

        # Auto-promote pawns on promotion rows (FMJD: can't exist in a legal game)
        # Black pawns on row 7 (white's back rank) → black kings
        for x in range(BOARD_SIZE):
            if grid[7, x] == 1:  # BLACK pawn
                grid[7, x] = 2   # BLACK_KING
        # White pawns on row 0 (black's back rank) → white kings
        for x in range(BOARD_SIZE):
            if grid[0, x] == -1:  # WHITE pawn
                grid[0, x] = -2   # WHITE_KING

        # Count pieces
        flat = grid.ravel()
        b_count = int(np.count_nonzero(flat > 0))
        w_count = int(np.count_nonzero(flat < 0))

        # Block: no pieces at all
        if b_count == 0 and w_count == 0:
            QMessageBox.warning(self, "Ошибка", "Доска пуста. Расставьте шашки.")
            return None

        # Block: one side has no pieces
        if b_count == 0:
            QMessageBox.warning(self, "Ошибка", "У чёрных нет шашек.")
            return None
        if w_count == 0:
            QMessageBox.warning(self, "Ошибка", "У белых нет шашек.")
            return None

        # Warn: more than 12 pieces per side (non-standard, but allowed)
        warnings = []
        if b_count > 12:
            warnings.append(f"У чёрных {b_count} шашек (макс. 12 в стандартной игре)")
        if w_count > 12:
            warnings.append(f"У белых {w_count} шашек (макс. 12 в стандартной игре)")
        if warnings:
            self.setWindowTitle(f"{APP_NAME} — {'; '.join(warnings)}")

        return board

    def _editor_play_from_here(self):
        """Exit editor and start a game from the edited position."""
        board = self._editor_validate_and_fix()
        if board is None:
            return
        side = self._editor_side()
        self.exit_editor_mode()
        self._start_game_from_position(board, side)

    def _editor_analyze_from_here(self):
        """Exit editor, start game from position, and open the analysis pane."""
        board = self._editor_validate_and_fix()
        if board is None:
            return
        side = self._editor_side()
        self.exit_editor_mode()
        self._start_game_from_position(board, side)
        # Open the analysis pane via the proper toggle path so window
        # size is unlocked and _pane_saved_size is captured correctly.
        self._act_toggle_pane.setChecked(True)
        self._on_toggle_analysis_pane(True)

    def _editor_cancel(self):
        """Cancel editing and restore the previous game state."""
        self.exit_editor_mode()
        # Restore snapshot
        self._controller._positions = self._editor_saved_positions
        self._controller._replay_history = self._editor_saved_replay
        self._controller._ply_count = self._editor_saved_ply
        self._controller._current_turn = self._editor_saved_turn
        self._controller._player_color = self._editor_saved_player_color
        self._controller.board = self._editor_saved_board
        self._controller._position_counts = self._editor_saved_position_counts
        self._controller.board_changed.emit()
        self._controller.turn_changed.emit(self._controller._current_turn)
        self._controller.selection_changed.emit(None, None)
        self._controller.capture_highlights_changed.emit([])

        # If it was the computer's turn when editor was entered, restart AI.
        # enter_editor_mode kills the AI thread, so we must re-launch it.
        if self._controller._current_turn == self._controller._computer_color:
            self._controller._start_computer_turn()

    def _start_game_from_position(self, board, turn: Color):
        """Start a new game from a custom board position and side-to-move."""
        self._controller.new_game_from_position(board, turn)

    # --- UI helpers ---

    def _update_action_states(self):
        """Centralized action state management.

        All enable/disable logic for menu actions lives here.
        Called after every state change: board changed, AI started/stopped,
        editor entered/exited, game loaded.

        Three modes: EDITOR, AI_THINKING, NORMAL (playing).
        """
        editor = self.board_widget.editor_mode
        thinking = self._controller.is_thinking
        has_moves = self._controller.can_undo
        has_game = self._controller.can_save

        # --- Игра menu ---
        self._act_new.setEnabled(not editor and not thinking)
        self._act_load.setEnabled(not editor and not thinking)
        self._act_save.setEnabled(not editor and not thinking and has_game)
        self._act_undo.setEnabled(not editor and not thinking and has_moves)
        self._act_hint.setEnabled(not editor and not thinking)
        # Flip sides (D36) — allowed only on the player's turn to prevent
        # swap-spam from turning the game into AI-vs-AI. Blocked in editor
        # (which has its own side-to-move widget).
        on_player_turn = self._controller.current_turn == self._controller.player_color
        self._act_flip.setEnabled(not editor and not thinking and on_player_turn)
        # Resign — allowed any time a game is in progress and outside editor.
        self._act_resign.setEnabled(not editor and has_game)
        # _act_exit — always enabled

        # --- Настройки ---
        self._act_options.setEnabled(not editor and not thinking)

        # --- Тренировка ---
        self._act_puzzles.setEnabled(not editor and not thinking)

        # --- Вид ---
        self._act_playback.setEnabled(not editor and has_game)

        # --- Позиция ---
        self._act_editor.setEnabled(not editor and not thinking)
        self._act_copy_fen.setEnabled(True)  # always available
        self._act_paste_fen.setEnabled(not editor and not thinking)

        # --- Анализ ---
        self._act_toggle_pane.setEnabled(not editor)
        self._act_analyze_game.setEnabled(not editor and not thinking and has_game)

    # --- Keyboard events ---

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.board_widget.editor_mode:
            self._editor_cancel()
            return
        if event.key() == Qt.Key.Key_F3:
            self._act_toggle_pane.setChecked(not self._act_toggle_pane.isChecked())
            self._on_toggle_analysis_pane(self._act_toggle_pane.isChecked())
            return
        super().keyPressEvent(event)

    # --- Close event ---

    def closeEvent(self, event):
        event.accept()
