"""Game controller — ties together Board, AI, UI, and saves.

Central coordinator managing game state, turn logic, player input
validation, AI execution (in a worker thread), and save/load.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from draughts.config import AUTOSAVE_FILENAME, BOARD_SIZE, Color, GameSettings, get_data_dir
from draughts.game.ai import AIEngine, AIMove
from draughts.game.board import Board
from draughts.game.save import GameSave, autosave, load_game, save_game

logger = logging.getLogger("draughts.controller")


class AIWorker(QObject):
    """Runs AI computation in a background thread."""

    finished = pyqtSignal(object)  # AIMove | None

    def __init__(self, board: Board, engine: AIEngine):
        super().__init__()
        self._board = board
        self._engine = engine

    def run(self):
        try:
            result = self._engine.find_move(self._board.copy())
        except Exception:
            logger.exception("AI crashed during find_move")
            result = None
        self.finished.emit(result)


class GameController(QObject):
    """Central game logic controller.

    Signals:
        board_changed: board was updated, UI should repaint
        turn_changed: whose turn it is now ('w' or 'b')
        game_over: (message) — game ended
        ai_thinking: (bool) — AI started/finished thinking
        selection_changed: (x, y) or (None, None) — piece selection changed
        capture_highlights_changed: list of (x, y) — multi-capture intermediate squares
    """

    board_changed = pyqtSignal()
    turn_changed = pyqtSignal(str)
    game_over = pyqtSignal(str)
    message_changed = pyqtSignal(str)
    ai_thinking = pyqtSignal(bool)
    selection_changed = pyqtSignal(object, object)
    capture_highlights_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.board = Board()
        self.settings = GameSettings()

        # Game state
        self._current_turn: Color = Color.WHITE
        self._computer_color: Color = Color.BLACK
        self._player_color: Color = Color.WHITE
        self._selected: tuple[int, int] | None = None
        self._capture_path: list[tuple[int, int]] = []

        # History
        self._positions: list[str] = []
        self._replay_history: list[str] = []
        self._ply_count: int = 0
        self._game_started: bool = False

        # AI thread
        self._ai_thread: QThread | None = None
        self._ai_worker: AIWorker | None = None

        # Messages
        self._messages = self._load_messages()

        # Record initial position
        self._positions.append(self.board.to_position_string())
        self._replay_history.append(self.board.to_position_string())

    def _load_messages(self) -> list[str]:
        msg_path = Path(__file__).parent.parent / "resources" / "messages.txt"
        try:
            text = msg_path.read_text(encoding="utf-8")
            return [line.strip() for line in text.strip().split("\n") if line.strip()]
        except (FileNotFoundError, UnicodeDecodeError):
            return ["Думаю..."]

    # --- New game ---

    def new_game(self):
        """Reset everything for a new game."""
        self.board = Board()
        self._current_turn = Color.WHITE
        self._computer_color = Color.BLACK if not self.settings.invert_color else Color.WHITE
        self._player_color = Color.WHITE if not self.settings.invert_color else Color.BLACK
        self._selected = None
        self._capture_path = []
        self._positions = [self.board.to_position_string()]
        self._replay_history = [self.board.to_position_string()]
        self._ply_count = 0
        self._game_started = False

        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

        if self.settings.invert_color:
            self._start_computer_turn()

    # --- Player input ---

    def on_cell_left_click(self, x: int, y: int):
        """Handle left-click on board cell."""
        if self._current_turn != self._player_color:
            return
        if self._ai_thread is not None:
            return

        piece = self.board.piece_at(x, y)

        if self._selected is None:
            if self._is_player_piece(piece):
                self._select_piece(x, y)
            return

        sx, sy = self._selected

        if self._is_player_piece(piece) and (x, y) != (sx, sy) and not self._capture_path:
            self._select_piece(x, y)
            return

        if piece == Board.EMPTY:
            self._try_move(sx, sy, x, y)

    def on_cell_right_click(self, x: int, y: int):
        """Handle right-click — intermediate capture position."""
        if self._current_turn != self._player_color:
            return
        if self._selected is None:
            return

        sx, sy = self._selected

        virtual = self.board.copy()
        current_pos = (sx, sy)

        if self._capture_path:
            piece = virtual.piece_at(sx, sy)
            for i in range(len(self._capture_path) - 1):
                fx, fy = self._capture_path[i]
                tx, ty = self._capture_path[i + 1]
                dx = 1 if tx > fx else -1
                dy = 1 if ty > fy else -1
                cx, cy = fx + dx, fy + dy
                while (cx, cy) != (tx, ty):
                    if virtual.piece_at(cx, cy) != Board.EMPTY:
                        virtual.place_piece(cx, cy, Board.EMPTY)
                        break
                    cx += dx
                    cy += dy
                virtual.place_piece(fx, fy, Board.EMPTY)
                virtual.place_piece(tx, ty, piece)
            current_pos = self._capture_path[-1]

        captures = virtual.get_captures(*current_pos)

        for path in captures:
            if len(path) >= 2 and path[1] == (x, y):
                if not self._capture_path:
                    self._capture_path = [(sx, sy), (x, y)]
                else:
                    self._capture_path.append((x, y))
                self.capture_highlights_changed.emit(self._capture_path[1:])
                return

    def _is_player_piece(self, piece: int) -> bool:
        return self.board.is_white(piece) if self._player_color == Color.WHITE else self.board.is_black(piece)

    def _select_piece(self, x: int, y: int):
        """Select a piece for moving."""
        if self.board.has_any_capture(self._player_color):
            captures = self.board.get_captures(x, y)
            if not captures:
                if self.settings.remind:
                    self._find_and_signal_capture()
                return

        self._selected = (x, y)
        self._capture_path = []
        self.selection_changed.emit(x, y)
        self.capture_highlights_changed.emit([])

    def _find_and_signal_capture(self):
        """Find a piece that must capture and signal it."""
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                piece = self.board.piece_at(x, y)
                if self._is_player_piece(piece) and self.board.get_captures(x, y):
                    self.message_changed.emit(f"Шашка {Board.pos_to_notation(x, y)} должна бить!")
                    return

    def _try_move(self, sx: int, sy: int, tx: int, ty: int):
        """Try to execute a move from (sx, sy) to (tx, ty)."""
        if self.board.has_any_capture(self._player_color):
            self._try_capture_move(sx, sy, tx, ty)
        else:
            self._try_normal_move(sx, sy, tx, ty)

    def _try_normal_move(self, sx: int, sy: int, tx: int, ty: int):
        """Try a non-capture move."""
        valid_moves = self.board.get_valid_moves(sx, sy)
        if (tx, ty) not in valid_moves:
            return

        notation = f"{Board.pos_to_notation(sx, sy)}-{Board.pos_to_notation(tx, ty)}"
        self.board.execute_move(sx, sy, tx, ty)
        self._finish_player_move(notation)

    def _try_capture_move(self, sx: int, sy: int, tx: int, ty: int):
        """Try a capture move."""
        full_path = [*self._capture_path, (tx, ty)] if self._capture_path else [(sx, sy), (tx, ty)]

        captures = self.board.get_captures(sx, sy)
        matching = [p for p in captures if p[: len(full_path)] == full_path and len(p) == len(full_path)]

        if not matching:
            partial = [p for p in captures if len(p) > len(full_path) and p[: len(full_path)] == full_path]
            if partial:
                if not self._capture_path:
                    self._capture_path = [(sx, sy), (tx, ty)]
                else:
                    self._capture_path.append((tx, ty))
                self.capture_highlights_changed.emit(self._capture_path[1:])
                return
            return

        best_path = matching[0]
        self.board.execute_capture_path(best_path)

        notation = ":".join(Board.pos_to_notation(x, y) for x, y in best_path)
        self._finish_player_move(notation)

    def _finish_player_move(self, notation: str):
        """Finalize player's move — record, switch turns, start AI."""
        self._ply_count += 1
        self._game_started = True
        self._selected = None
        self._capture_path = []

        pos = self.board.to_position_string()
        self._positions.append(pos)
        self._replay_history.append(pos)

        self.board_changed.emit()
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

        if self._check_game_over():
            return

        self._do_autosave()

        self._current_turn = self._computer_color
        self.turn_changed.emit(self._current_turn)
        self._start_computer_turn()

    # --- Computer turn ---

    def _start_computer_turn(self):
        """Start the AI computation in a background thread."""
        msg = random.choice(self._messages) if self._messages else "Думаю..."
        self.message_changed.emit(msg)
        self.ai_thinking.emit(True)

        self._ai_thread = QThread()
        engine = AIEngine(
            difficulty=self.settings.difficulty,
            color=self._computer_color,
            search_depth=self.settings.search_depth,
        )
        self._ai_worker = AIWorker(self.board, engine)
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._on_ai_finished)
        self._ai_thread.start()

    def _on_ai_finished(self, result: AIMove | None):
        """Handle AI computation result."""
        try:
            self._on_ai_finished_inner(result)
        except Exception:
            logger.exception("CRASH in _on_ai_finished")

    def _on_ai_finished_inner(self, result: AIMove | None):
        self.ai_thinking.emit(False)
        self.message_changed.emit("")

        if self._ai_thread is not None:
            self._ai_thread.quit()
            self._ai_thread.wait()
            self._ai_worker.deleteLater()
            self._ai_thread.deleteLater()
            self._ai_worker = None
            self._ai_thread = None

        if result is None:
            self.game_over.emit("Вы выиграли!")
            return

        if result.kind == "capture":
            self.board.execute_capture_path(result.path)
        elif result.kind in ("move", "sacrifice"):
            x1, y1 = result.path[0]
            x2, y2 = result.path[1]
            self.board.execute_move(x1, y1, x2, y2)
        else:
            logger.warning(f"Unknown AI move kind: {result.kind}")
            return

        self._ply_count += 1

        pos = self.board.to_position_string()
        self._positions.append(pos)
        self._replay_history.append(pos)

        self.board_changed.emit()

        if self._check_game_over():
            return

        self._do_autosave()

        self._current_turn = self._player_color
        self.turn_changed.emit(self._current_turn)

    # --- Undo ---

    def undo_move(self):
        """Undo the last move (player + computer response). Only on difficulty 1."""
        if self.settings.difficulty != 1:
            return
        if self._ply_count < 2:
            return
        if self._ai_thread is not None:
            return

        self._ply_count -= 2
        if len(self._positions) > self._ply_count + 1:
            self._positions = self._positions[: self._ply_count + 1]
        if len(self._replay_history) > self._ply_count + 1:
            self._replay_history = self._replay_history[: self._ply_count + 1]

        self.board.load_from_position_string(self._positions[-1])

        self._selected = None
        self._capture_path = []
        self._current_turn = self._player_color

        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

    # --- Game over ---

    def _check_game_over(self) -> bool:
        """Check if the game is over. Emit game_over signal if so."""
        w_count = self.board.count_pieces(Color.WHITE)
        b_count = self.board.count_pieces(Color.BLACK)

        if w_count == 0:
            player_lost = self._player_color == Color.WHITE
            self.game_over.emit("Вы проиграли!" if player_lost else "Вы выиграли!")
            return True

        if b_count == 0:
            player_lost = self._player_color == Color.BLACK
            self.game_over.emit("Вы проиграли!" if player_lost else "Вы выиграли!")
            return True

        next_turn = self._player_color if self._current_turn == self._computer_color else self._computer_color
        if not self.board.has_any_move(next_turn):
            if next_turn == self._player_color:
                self.game_over.emit("Вы проиграли!")
            else:
                self.game_over.emit("Вы выиграли!")
            return True

        return False

    # --- Save / Load ---

    def save_current_game(self, filepath: str):
        """Save current game to file."""
        gs = GameSave(
            difficulty=self.settings.difficulty,
            speed=1,
            remind=self.settings.remind,
            sound_effect=False,
            pause=self.settings.pause,
            positions=list(self._positions),
            replay_positions=list(self._replay_history),
        )
        save_game(filepath, gs)

    def load_saved_game(self, filepath: str):
        """Load a game from file."""
        gs = load_game(filepath)
        self.settings.difficulty = gs.difficulty
        self.settings.remind = gs.remind
        self.settings.pause = gs.pause

        self._positions = list(gs.positions)
        self._replay_history = list(gs.replay_positions) if gs.replay_positions else list(gs.positions)
        self._ply_count = len(self._positions) - 1

        if self._positions:
            self.board.load_from_position_string(self._positions[-1])
        else:
            self.board = Board()

        self._current_turn = Color.WHITE if self._ply_count % 2 == 0 else Color.BLACK
        self._selected = None
        self._capture_path = []

        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

        if self._current_turn == self._computer_color:
            self._start_computer_turn()

    def _do_autosave(self):
        """Auto-save current game state."""
        try:
            filepath = str(get_data_dir() / AUTOSAVE_FILENAME)
            gs = GameSave(
                difficulty=self.settings.difficulty,
                speed=1,
                remind=self.settings.remind,
                sound_effect=False,
                pause=self.settings.pause,
                positions=list(self._positions),
                replay_positions=list(self._replay_history),
            )
            autosave(filepath, gs)
        except Exception:
            pass

    # --- Properties ---

    @property
    def current_turn(self) -> Color:
        return self._current_turn

    @property
    def player_color(self) -> Color:
        return self._player_color

    @property
    def computer_color(self) -> Color:
        return self._computer_color

    @property
    def replay_history(self) -> list[str]:
        return list(self._replay_history)

    @property
    def can_undo(self) -> bool:
        return self.settings.difficulty == 1 and self._ply_count >= 2

    @property
    def can_save(self) -> bool:
        return self._ply_count >= 1
