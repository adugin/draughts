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

from draughts.config import BOARD_PX, Color
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
        self.setWindowTitle("Шашки")
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

        # Clock toolbar (D19) — shown only when settings.show_clock is True
        self._clock_toolbar = QToolBar("Часы", self)
        self._clock_toolbar.setMovable(False)
        self._clock_toolbar.setFloatable(False)
        # Clock toolbar inherits colors from the window-level theme QSS.
        # Only set font here (not colors).
        self._clock_label_white = QLabel("\u26aa 0:00")
        self._clock_label_black = QLabel("\u26ab 0:00")
        self._clock_toolbar.addWidget(self._clock_label_white)
        self._clock_toolbar.addSeparator()
        self._clock_toolbar.addWidget(self._clock_label_black)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self._clock_toolbar)
        self._clock_toolbar.setVisible(False)

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

        self._act_hint = QAction("&Подсказка", self)
        self._act_hint.setShortcut(QKeySequence("Ctrl+H"))
        self._act_hint.triggered.connect(self._on_hint)
        game_menu.addAction(self._act_hint)

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
        self._act_editor.setShortcut(QKeySequence("E"))
        self._act_editor.triggered.connect(self.enter_editor_mode)
        position_menu.addAction(self._act_editor)

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
        self._act_analyze_game.setEnabled(False)
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
        c.clock_updated.connect(self._on_clock_updated)
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

    def _on_last_move_changed(self, move):
        """Propagate last-move highlight to board widget."""
        self.board_widget.last_move = move

    def _on_hint_ready(self, squares: list, message: str):
        """Display the hint squares on the board and show a status message (D16)."""
        self.board_widget.hint_squares = squares
        # Show as a transient message box in the title bar area
        self.setWindowTitle(f"Шашки — {message}")
        # Restore plain title after 4 seconds
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(4000, lambda: self.setWindowTitle("Шашки"))

    def _on_message_changed(self, message: str):
        """Show controller messages (thinking, mandatory capture hints) in title bar."""
        if message:
            self.setWindowTitle(f"Шашки — {message}")
        else:
            self.setWindowTitle("Шашки")

    def _on_clock_updated(self, white_ms: int, black_ms: int):
        """Update clock labels (D19)."""

        def fmt(ms: int) -> str:
            total_s = ms // 1000
            m, s = divmod(total_s, 60)
            return f"{m}:{s:02d}"

        self._clock_label_white.setText(f"\u26aa {fmt(white_ms)}")
        self._clock_label_black.setText(f"\u26ab {fmt(black_ms)}")

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
            self.board_widget.set_theme(new_theme)
            if new_theme != self._current_theme:
                self._apply_theme(new_theme)
            # Apply board orientation (D22)
            self.board_widget.inverted = self._controller.settings.invert_color
            # Show/hide clock toolbar (D19)
            self._clock_toolbar.setVisible(self._controller.settings.show_clock)
            # Apply tuned eval toggle immediately (BUG-004)
            from draughts.game.ai.eval import set_use_tuned_eval

            set_use_tuned_eval(self._controller.settings.use_tuned_eval)

            # If player switched sides, start a new game so the
            # computer moves first when it's now white.
            if old_invert != new_invert:
                self._controller.new_game()

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
            # Re-lock: shrink window back to board-only size
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, self._relock_size)

    def _relock_size(self) -> None:
        """Re-lock window size after dock widget is hidden."""
        self.adjustSize()
        self.setFixedSize(self.size())

    def _on_pane_visibility_changed(self, visible: bool) -> None:
        """Keep the menu checkbox synced with the dock widget's actual visibility."""
        self._act_toggle_pane.setChecked(visible)
        if not visible:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, self._relock_size)

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

        # Stop any running AI
        if self._controller._ai_thread is not None:
            self._controller._ai_thread.quit()
            self._controller._ai_thread.wait()
            self._controller._ai_worker = None
            self._controller._ai_thread = None
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

        # Build the editor toolbar
        self._editor_toolbar = QToolBar("Редактор позиции", self)
        self._editor_toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._editor_toolbar)

        # Side-to-move radio buttons
        _tc = get_theme_colors(self._current_theme)
        lbl = QLabel("Ход:")
        lbl.setStyleSheet(f"color: {_tc['fg']}; font-weight: bold; padding: 0 4px;")
        self._editor_toolbar.addWidget(lbl)

        self._editor_radio_white = QRadioButton("Белые")
        self._editor_radio_black = QRadioButton("Чёрные")

        self._editor_side_group = QButtonGroup(self)
        self._editor_side_group.addButton(self._editor_radio_white)
        self._editor_side_group.addButton(self._editor_radio_black)

        if self._editor_turn == Color.WHITE:
            self._editor_radio_white.setChecked(True)
        else:
            self._editor_radio_black.setChecked(True)

        self._editor_toolbar.addWidget(self._editor_radio_white)
        self._editor_toolbar.addWidget(self._editor_radio_black)
        self._editor_toolbar.addSeparator()

        # Action buttons
        btn_clear = QPushButton("Очистить доску")
        btn_clear.clicked.connect(self._editor_clear_board)
        self._editor_toolbar.addWidget(btn_clear)

        btn_start = QPushButton("Начальная позиция")
        btn_start.clicked.connect(self._editor_start_position)
        self._editor_toolbar.addWidget(btn_start)

        self._editor_toolbar.addSeparator()

        btn_import = QPushButton("Импорт FEN")
        btn_import.clicked.connect(self._editor_import_fen)
        self._editor_toolbar.addWidget(btn_import)

        btn_export = QPushButton("Экспорт FEN")
        btn_export.clicked.connect(self._editor_export_fen)
        self._editor_toolbar.addWidget(btn_export)

        self._editor_toolbar.addSeparator()

        btn_play = QPushButton("▶ Играть отсюда")
        btn_play.setStyleSheet(f"font-weight: bold; color: {_tc['editor_play_fg']};")
        btn_play.clicked.connect(self._editor_play_from_here)
        self._editor_toolbar.addWidget(btn_play)

        btn_analyze = QPushButton("Анализ отсюда")
        btn_analyze.clicked.connect(self._editor_analyze_from_here)
        self._editor_toolbar.addWidget(btn_analyze)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setStyleSheet(f"color: {_tc['editor_cancel_fg']};")
        btn_cancel.clicked.connect(self._editor_cancel)
        self._editor_toolbar.addWidget(btn_cancel)

        # Disable game actions while editing
        self._act_new.setEnabled(False)
        self._act_load.setEnabled(False)
        self._act_save.setEnabled(False)
        self._act_undo.setEnabled(False)

    def exit_editor_mode(self):
        """Exit editor mode and remove the toolbar."""
        if not self.board_widget.editor_mode:
            return
        self.board_widget.editor_mode = False
        if hasattr(self, "_editor_toolbar") and self._editor_toolbar is not None:
            self.removeToolBar(self._editor_toolbar)
            self._editor_toolbar.deleteLater()
            self._editor_toolbar = None
        self._act_new.setEnabled(True)
        self._act_load.setEnabled(True)
        self._update_action_states()

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

    def _editor_play_from_here(self):
        """Exit editor and start a game from the edited position."""
        side = self._editor_side()
        board = self._editor_board.copy()
        self.exit_editor_mode()
        self._start_game_from_position(board, side)

    def _editor_analyze_from_here(self):
        """Exit editor, start game from position, and open the analysis pane."""
        side = self._editor_side()
        board = self._editor_board.copy()
        self.exit_editor_mode()
        self._start_game_from_position(board, side)
        # Open the analysis pane and prime it with the new position
        self._analysis_pane.show()
        self._act_toggle_pane.setChecked(True)
        self._analysis_pane.set_position(board, side)

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
        self._act_undo.setEnabled(self._controller.can_undo)
        self._act_save.setEnabled(self._controller.can_save)
        self._act_analyze_game.setEnabled(self._controller.can_save)

    # --- Keyboard events ---

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.board_widget.editor_mode:
            self._editor_play_from_here()
            return
        if event.key() == Qt.Key.Key_F3:
            self._act_toggle_pane.setChecked(not self._act_toggle_pane.isChecked())
            self._on_toggle_analysis_pane(self._act_toggle_pane.isChecked())
            return
        super().keyPressEvent(event)

    # --- Close event ---

    def closeEvent(self, event):
        event.accept()
