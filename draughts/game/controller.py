"""Game controller — ties together Board, AI, UI, saves, and learning.

This is the central coordinator. It manages:
- Game state and turn logic
- Player input validation
- AI turn execution (in a worker thread)
- Move notation recording
- Save/load
- Learning DB updates
- Timer countdown
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

logger = logging.getLogger('draughts.controller')

from draughts.config import AUTOSAVE_FILENAME, LEARNING_DB_FILENAME, GameSettings, get_data_dir
from draughts.game.ai import AIMove, computer_move, record_learning
from draughts.game.board import Board
from draughts.game.learning import LearningDB
from draughts.game.save import GameSave, autosave, load_game, save_game
from draughts.ui.sounds import SoundManager


class AIWorker(QObject):
    """Runs AI computation in a background thread."""

    finished = pyqtSignal(object)  # AIMove | None

    def __init__(self, board: Board, difficulty: int, use_base: bool,
                 learning_db: LearningDB | None, color: str):
        super().__init__()
        self._board = board
        self._difficulty = difficulty
        self._use_base = use_base
        self._learning_db = learning_db
        self._color = color

    def run(self):
        try:
            result = computer_move(
                self._board.copy(),
                difficulty=self._difficulty,
                use_base=self._use_base,
                learning_db=self._learning_db,
                color=self._color,
            )
        except Exception:
            logger.exception("AI crashed during computer_move")
            result = None
        self.finished.emit(result)


class GameController(QObject):
    """Central game logic controller.

    Signals:
        board_changed: board was updated, UI should repaint
        turn_changed: whose turn it is now ('w' or 'b')
        notation_added: (move_text, color) — new move to show in notation
        game_over: (message) — game ended
        message_changed: (text) — status/AI message update
        captured_changed: (white_count, black_count) — captured pieces count changed
        timer_tick: (seconds_remaining) — timer update
        ai_thinking: (bool) — AI started/finished thinking
        selection_changed: (x, y) or (None, None) — piece selection changed
        capture_highlights_changed: list of (x, y) — multi-capture intermediate squares
    """

    board_changed = pyqtSignal()
    turn_changed = pyqtSignal(str)
    notation_added = pyqtSignal(str, str)
    game_over = pyqtSignal(str)
    message_changed = pyqtSignal(str)
    captured_changed = pyqtSignal(int, int)
    timer_tick = pyqtSignal(int)
    ai_thinking = pyqtSignal(bool)
    selection_changed = pyqtSignal(object, object)
    capture_highlights_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.board = Board()
        self.settings = GameSettings()
        self.learning_db = self._load_learning_db()
        self.sounds = SoundManager()

        # Game state
        self._current_turn: str = 'w'  # who moves next
        self._computer_color: str = 'b'  # AI plays black by default
        self._player_color: str = 'w'
        self._selected: tuple[int, int] | None = None
        self._capture_path: list[tuple[int, int]] = []
        self._pending_captures: set[tuple[int, int]] = set()
        self._must_capture_from: tuple[int, int] | None = None

        # History
        self._positions: list[str] = []  # board state after each half-move
        self._replay_history: list[str] = []  # full game for playback
        self._ply_count: int = 0  # half-move counter
        self._white_captured_count: int = 0  # captured white pieces count
        self._black_captured_count: int = 0  # captured black pieces count
        self._game_started: bool = False

        # AI thread
        self._ai_thread: QThread | None = None
        self._ai_worker: AIWorker | None = None

        # Timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)
        self._time_remaining: int = 0

        # Messages
        self._messages = self._load_messages()

        # Record initial position
        self._positions.append(self.board.to_position_string())
        self._replay_history.append(self.board.to_position_string())

    # --- Initialization ---

    def _load_learning_db(self) -> LearningDB:
        db_path = get_data_dir() / LEARNING_DB_FILENAME
        return LearningDB(str(db_path))

    def _load_messages(self) -> list[str]:
        msg_path = Path(__file__).parent.parent / "resources" / "messages.txt"
        try:
            text = msg_path.read_text(encoding="utf-8")
            return [line.strip() for line in text.strip().split('\n') if line.strip()]
        except (FileNotFoundError, UnicodeDecodeError):
            return ["Думаю..."]

    # --- New game ---

    def new_game(self):
        """Reset everything for a new game."""
        self.board = Board()
        self._current_turn = 'w'
        self._computer_color = 'b' if not self.settings.invert_color else 'w'
        self._player_color = 'w' if not self.settings.invert_color else 'b'
        self._selected = None
        self._capture_path = []
        self._pending_captures = set()
        self._must_capture_from = None
        self._positions = [self.board.to_position_string()]
        self._replay_history = [self.board.to_position_string()]
        self._ply_count = 0
        self._white_captured_count = 0
        self._black_captured_count = 0
        self._game_started = False

        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.captured_changed.emit(self._white_captured_count, self._black_captured_count)
        self.message_changed.emit("")
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

        # If computer moves first (inverted colors)
        if self.settings.invert_color:
            self._start_computer_turn()
        else:
            self._start_player_timer()

    # --- Player input ---

    def on_cell_left_click(self, x: int, y: int):
        """Handle left-click on board cell."""
        if self._current_turn != self._player_color:
            return  # not player's turn
        if self._ai_thread is not None:
            return  # AI is thinking

        piece = self.board.piece_at(x, y)

        # If no piece selected yet — try to select one
        if self._selected is None:
            if self._is_player_piece(piece):
                self._select_piece(x, y)
            return

        # A piece is already selected
        sx, sy = self._selected

        # Clicking on another own piece — reselect
        if self._is_player_piece(piece) and (x, y) != (sx, sy) and not self._capture_path:
            self._select_piece(x, y)
            return

        # Trying to move to empty cell
        if piece == Board.EMPTY:
            self._try_move(sx, sy, x, y)

    def on_cell_right_click(self, x: int, y: int):
        """Handle right-click — intermediate capture position."""
        logger.info(f"Right click: ({x}, {y}), selected={self._selected}, "
                     f"capture_path={self._capture_path}")
        if self._current_turn != self._player_color:
            return
        if self._selected is None:
            return

        sx, sy = self._selected

        # Build a virtual board reflecting captures already marked
        virtual = self.board.copy()
        current_pos = (sx, sy)
        captured_so_far = set()

        if self._capture_path:
            # Simulate the partial capture path on a virtual board
            piece = virtual.piece_at(sx, sy)
            for i in range(len(self._capture_path) - 1):
                fx, fy = self._capture_path[i]
                tx, ty = self._capture_path[i + 1]
                # Find captured piece between fx,fy and tx,ty
                dx = 1 if tx > fx else -1
                dy = 1 if ty > fy else -1
                cx, cy = fx + dx, fy + dy
                while (cx, cy) != (tx, ty):
                    if virtual.piece_at(cx, cy) != Board.EMPTY:
                        captured_so_far.add((cx, cy))
                        virtual.place_piece(cx, cy, Board.EMPTY)
                        break
                    cx += dx
                    cy += dy
                virtual.place_piece(fx, fy, Board.EMPTY)
                virtual.place_piece(tx, ty, piece)
            current_pos = self._capture_path[-1]

        # Now check captures from current position on virtual board
        captures = virtual.get_captures(*current_pos)
        logger.debug(f"Virtual captures from {current_pos}: {len(captures)} paths")

        for path in captures:
            if len(path) >= 2 and path[1] == (x, y):
                # Valid intermediate jump
                if not self._capture_path:
                    self._capture_path = [(sx, sy), (x, y)]
                else:
                    self._capture_path.append((x, y))
                self.capture_highlights_changed.emit(self._capture_path[1:])
                logger.info(f"Intermediate capture marked: {self._capture_path}")
                return
        logger.debug(f"Right click ({x},{y}) not a valid intermediate capture")

    def _is_player_piece(self, piece: str) -> bool:
        if self._player_color == 'w':
            return self.board.is_white(piece)
        else:
            return self.board.is_black(piece)

    def _select_piece(self, x: int, y: int):
        """Select a piece for moving."""
        # Check if mandatory capture exists
        if self.board.has_any_capture(self._player_color):
            # Can only select pieces that can capture
            captures = self.board.get_captures(x, y)
            if not captures:
                # This piece can't capture — remind player
                if self.settings.remind:
                    self._find_and_signal_capture()
                return

        self._selected = (x, y)
        self._capture_path = []
        self._pending_captures = set()
        self.selection_changed.emit(x, y)
        self.capture_highlights_changed.emit([])

    def _find_and_signal_capture(self):
        """Find a piece that must capture and signal it."""
        for y in range(1, 9):
            for x in range(1, 9):
                piece = self.board.piece_at(x, y)
                if self._is_player_piece(piece):
                    if self.board.get_captures(x, y):
                        self.message_changed.emit(
                            f"Шашка {Board.pos_to_notation(x, y)} должна бить!")
                        return

    def _try_move(self, sx: int, sy: int, tx: int, ty: int):
        """Try to execute a move from (sx, sy) to (tx, ty)."""
        must_capture = self.board.has_any_capture(self._player_color)

        if must_capture:
            self._try_capture_move(sx, sy, tx, ty)
        else:
            self._try_normal_move(sx, sy, tx, ty)

    def _try_normal_move(self, sx: int, sy: int, tx: int, ty: int):
        """Try a non-capture move."""
        valid_moves = self.board.get_valid_moves(sx, sy)
        if (tx, ty) not in valid_moves:
            if self.settings.sound_effect:
                self.sounds.play_error()
            return  # invalid move

        # Execute move
        move_notation = f"{Board.pos_to_notation(sx, sy)}-{Board.pos_to_notation(tx, ty)}"
        self.board.execute_move(sx, sy, tx, ty)
        if self.settings.sound_effect:
            # Check for promotion
            if self.board.piece_at(tx, ty) in (Board.WHITE_KING, Board.BLACK_KING):
                self.sounds.play_king()
            else:
                self.sounds.play_move()
        self._finish_player_move(move_notation)

    def _try_capture_move(self, sx: int, sy: int, tx: int, ty: int):
        """Try a capture move."""
        if self._capture_path:
            # Multi-capture: append final position
            full_path = self._capture_path + [(tx, ty)]
        else:
            full_path = [(sx, sy), (tx, ty)]

        # Validate capture path
        captures = self.board.get_captures(sx, sy)
        matching = [p for p in captures if self._path_matches(p, full_path)]

        if not matching:
            # Check if this could be an intermediate step
            partial = [p for p in captures
                       if len(p) > len(full_path) and p[:len(full_path)] == full_path]
            if partial:
                # This is a valid intermediate step — add to path
                if not self._capture_path:
                    self._capture_path = [(sx, sy), (tx, ty)]
                else:
                    self._capture_path.append((tx, ty))
                self.capture_highlights_changed.emit(self._capture_path[1:])
                return
            return  # invalid capture

        # Execute the best matching capture
        best_path = matching[0]
        captured = self.board.execute_capture_path(best_path)
        if self.settings.sound_effect:
            self.sounds.play_capture()

        # Update captured counts
        for cx, cy in captured:
            # The pieces are already removed, but we know they were enemies
            if self._player_color == 'w':
                self._black_captured_count += 1
            else:
                self._white_captured_count += 1

        move_str = ":".join(Board.pos_to_notation(x, y) for x, y in best_path)
        self._finish_player_move(move_str)

    def _path_matches(self, full_path: list, partial: list) -> bool:
        """Check if a capture path starts with the given partial path."""
        if len(full_path) < len(partial):
            return False
        return full_path[:len(partial)] == partial and len(full_path) == len(partial)

    def _finish_player_move(self, notation: str):
        """Finalize player's move — record, switch turns, start AI."""
        self._ply_count += 1
        self._game_started = True
        self._selected = None
        self._capture_path = []

        # Record position
        pos = self.board.to_position_string()
        self._positions.append(pos)
        self._replay_history.append(pos)

        # Emit signals
        self.notation_added.emit(notation, self._player_color)
        self.board_changed.emit()
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])
        self.captured_changed.emit(self._white_captured_count, self._black_captured_count)
        self._stop_timer()

        # Check for game over
        if self._check_game_over():
            return

        # Auto-save
        self._do_autosave()

        # Switch to computer
        self._current_turn = self._computer_color
        self.turn_changed.emit(self._current_turn)
        self._start_computer_turn()

    # --- Computer turn ---

    def _start_computer_turn(self):
        """Start the AI computation in a background thread."""
        # Show thinking message
        msg = random.choice(self._messages) if self._messages else "Думаю..."
        self.message_changed.emit(msg)
        self.ai_thinking.emit(True)

        # Start AI in thread
        self._ai_thread = QThread()
        self._ai_worker = AIWorker(
            self.board, self.settings.difficulty,
            self.settings.use_base, self.learning_db,
            self._computer_color
        )
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
            self.message_changed.emit("Ошибка ИИ! См. debug.log")

    def _on_ai_finished_inner(self, result: AIMove | None):
        logger.debug(f"AI result: {result}")
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

        # Execute AI move
        board_before = self.board.copy()

        if result.kind == 'capture':
            captured = self.board.execute_capture_path(result.path)
            for _ in captured:
                if self._computer_color == 'b':
                    self._white_captured_count += 1
                else:
                    self._black_captured_count += 1
            notation = ":".join(Board.pos_to_notation(x, y) for x, y in result.path)
        elif result.kind in ('move', 'sacrifice'):
            x1, y1 = result.path[0]
            x2, y2 = result.path[1]
            self.board.execute_move(x1, y1, x2, y2)
            notation = f"{Board.pos_to_notation(x1, y1)}-{Board.pos_to_notation(x2, y2)}"
        else:
            logger.warning(f"Unknown AI move kind: {result.kind}")
            return

        self._ply_count += 1
        logger.debug(f"AI move: {notation}, ply={self._ply_count}")

        # Record position
        pos = self.board.to_position_string()
        self._positions.append(pos)
        self._replay_history.append(pos)

        # Learning
        if self.settings.use_base:
            self._do_learning(board_before, self.board)

        # Emit signals
        self.notation_added.emit(notation, self._computer_color)
        self.board_changed.emit()
        self.captured_changed.emit(self._white_captured_count, self._black_captured_count)

        if self._check_game_over():
            return

        # Auto-save
        self._do_autosave()

        # Switch to player
        self._current_turn = self._player_color
        self.turn_changed.emit(self._current_turn)
        self._start_player_timer()

    # --- Undo ---

    def undo_move(self):
        """Undo the last move (player + computer response). Only on difficulty 1."""
        if self.settings.difficulty != 1:
            return
        if self._ply_count < 2:
            return
        if self._ai_thread is not None:
            return

        # Go back 2 half-moves (player + computer)
        self._ply_count -= 2
        if len(self._positions) > self._ply_count + 1:
            self._positions = self._positions[:self._ply_count + 1]
        if len(self._replay_history) > self._ply_count + 1:
            self._replay_history = self._replay_history[:self._ply_count + 1]

        # Restore board
        self.board.load_from_position_string(self._positions[-1])

        # Recalculate captured counts
        self._recalculate_captures()

        self._selected = None
        self._capture_path = []
        self._current_turn = self._player_color

        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])
        self.captured_changed.emit(self._white_captured_count, self._black_captured_count)
        self._start_player_timer()

    def _recalculate_captures(self):
        """Recalculate captured piece counts from current board state."""
        w = self.board.count_pieces('w')
        b = self.board.count_pieces('b')
        self._white_captured_count = 12 - w
        self._black_captured_count = 12 - b

    # --- Timer ---

    def _start_player_timer(self):
        """Start the countdown timer for player's turn."""
        self._time_remaining = self.settings.period
        self.timer_tick.emit(self._time_remaining)
        self._timer.start(1000)

    def _stop_timer(self):
        self._timer.stop()

    def _on_timer_tick(self):
        self._time_remaining -= 1
        self.timer_tick.emit(self._time_remaining)
        if 0 < self._time_remaining <= 5 and self.settings.sound_effect:
            self.sounds.play_timer_warning()
        if self._time_remaining <= 0:
            self._stop_timer()
            # Time's up — confiscate or auto-play
            # For now, just warn
            self.message_changed.emit("Время вышло!")

    # --- Game over detection ---

    def _check_game_over(self) -> bool:
        """Check if the game is over. Emit game_over signal if so."""
        w_count = self.board.count_pieces('w')
        b_count = self.board.count_pieces('b')
        logger.debug(f"_check_game_over: w={w_count}, b={b_count}, turn={self._current_turn}")

        if w_count == 0:
            player_lost = (self._player_color == 'w')
            msg = "Вы проиграли!" if player_lost else "Вы выиграли!"
            logger.info(f"Game over: {msg} (no white pieces)")
            self.game_over.emit(msg)
            if self.settings.sound_effect:
                self.sounds.play_game_lose() if player_lost else self.sounds.play_game_win()
            self._on_game_end(winner='b')
            return True

        if b_count == 0:
            player_lost = (self._player_color == 'b')
            msg = "Вы проиграли!" if player_lost else "Вы выиграли!"
            logger.info(f"Game over: {msg} (no black pieces)")
            self.game_over.emit(msg)
            if self.settings.sound_effect:
                self.sounds.play_game_lose() if player_lost else self.sounds.play_game_win()
            self._on_game_end(winner='w')
            return True

        # Check if the OPPONENT of whoever just moved has any moves
        # After player moves, check computer; after computer moves, check player
        next_turn = self._player_color if self._current_turn == self._computer_color else self._computer_color
        logger.debug(f"Checking has_any_move for next turn: {next_turn}")
        if not self.board.has_any_move(next_turn):
            if next_turn == self._player_color:
                logger.info("Game over: player has no moves")
                self.game_over.emit("Вы проиграли!")
                self._on_game_end(winner=self._computer_color)
            else:
                logger.info("Game over: computer has no moves")
                self.game_over.emit("Вы выиграли!")
                self._on_game_end(winner=self._player_color)
            return True

        return False

    def _on_game_end(self, winner: str):
        """Handle game end — learning DB updates."""
        self._stop_timer()
        if self.settings.use_base and len(self._positions) >= 3:
            computer_won = (winner == self._computer_color)
            # Record last few positions
            if computer_won and self.settings.black_win:
                for pos_str in self._positions[-3:]:
                    self.learning_db.add_good(pos_str)
                self.learning_db.save()
            elif not computer_won and self.settings.black_lose:
                from draughts.game.learning import invert_position
                for pos_str in self._positions[-3:]:
                    self.learning_db.add_bad(invert_position(pos_str))
                self.learning_db.save()

    # --- Learning ---

    def _do_learning(self, board_before: Board, board_after: Board):
        """Record learning data after AI move."""
        if not self.settings.use_base or self.learning_db is None:
            return
        try:
            record_learning(
                self.learning_db, board_before, board_after,
                self._computer_color, won=False  # not known yet
            )
        except Exception:
            pass  # learning is non-critical

    # --- Save / Load ---

    def save_current_game(self, filepath: str):
        """Save current game to file."""
        gs = GameSave(
            difficulty=self.settings.difficulty,
            speed=self.settings.speed,
            remind=self.settings.remind,
            sound_effect=self.settings.sound_effect,
            pause=self.settings.pause,
            positions=list(self._positions),
            replay_positions=list(self._replay_history),
        )
        save_game(filepath, gs)

    def load_saved_game(self, filepath: str):
        """Load a game from file."""
        gs = load_game(filepath)
        self.settings.difficulty = gs.difficulty
        self.settings.speed = gs.speed
        self.settings.remind = gs.remind
        self.settings.sound_effect = gs.sound_effect
        self.settings.pause = gs.pause

        self._positions = list(gs.positions)
        self._replay_history = list(gs.replay_positions) if gs.replay_positions else list(gs.positions)
        self._ply_count = len(self._positions) - 1

        # Restore board from last position
        if self._positions:
            self.board.load_from_position_string(self._positions[-1])
        else:
            self.board = Board()

        self._recalculate_captures()

        # Determine whose turn
        # Even situation = white's turn, odd = black's turn
        self._current_turn = 'w' if self._ply_count % 2 == 0 else 'b'

        self._selected = None
        self._capture_path = []

        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.captured_changed.emit(self._white_captured_count, self._black_captured_count)
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])
        self.message_changed.emit("")

        if self._current_turn == self._computer_color:
            self._start_computer_turn()
        else:
            self._start_player_timer()

    def _do_autosave(self):
        """Auto-save current game state."""
        try:
            filepath = str(get_data_dir() / AUTOSAVE_FILENAME)
            gs = GameSave(
                difficulty=self.settings.difficulty,
                speed=self.settings.speed,
                remind=self.settings.remind,
                sound_effect=self.settings.sound_effect,
                pause=self.settings.pause,
                positions=list(self._positions),
                replay_positions=list(self._replay_history),
            )
            autosave(filepath, gs)
        except Exception:
            pass  # autosave is non-critical

    # --- Properties ---

    @property
    def current_turn(self) -> str:
        return self._current_turn

    @property
    def player_color(self) -> str:
        return self._player_color

    @property
    def computer_color(self) -> str:
        return self._computer_color

    @property
    def ply_count(self) -> int:
        return self._ply_count

    @property
    def replay_history(self) -> list[str]:
        return list(self._replay_history)

    @property
    def can_undo(self) -> bool:
        return self.settings.difficulty == 1 and self._ply_count >= 2

    @property
    def can_save(self) -> bool:
        return self._ply_count >= 1
