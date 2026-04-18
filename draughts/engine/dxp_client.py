"""DXP client — connects to a DXP server and plays one game.

Symmetric to dxp_server.py: the client sends GAMEREQ, receives GAMEACC,
then alternates MOVEs with the server. Used by tests and by engine-vs-
engine self-play over DXP.
"""

from __future__ import annotations

import logging
import socket
import time

from draughts.config import Color
from draughts.engine.dxp import DXPProtocolError, GameAcc, GameEnd, GameReq, Move, decode, encode, read_frame
from draughts.engine.dxp_server import _apply_move_to_board, _dxp_to_move_path, _move_to_dxp
from draughts.game.ai import AIEngine
from draughts.game.board import Board

logger = logging.getLogger("draughts.dxp.client")


def play_one_game(
    host: str = "127.0.0.1",
    port: int = 27531,
    *,
    our_color: str = "W",
    difficulty: int = 4,
    our_name: str = "DRAUGHTS-client",
) -> str:
    """Connect, negotiate, play one full game. Returns status string."""
    with socket.create_connection((host, port), timeout=60.0) as sock:
        fh = sock.makefile("rwb", buffering=0)

        fh.write(encode(GameReq(name=our_name, color=our_color, minutes=5, moves_to_end=0, setup="A")))

        frame = read_frame(fh)
        if not frame:
            return "bye"
        try:
            msg = decode(frame)
        except DXPProtocolError as e:
            logger.warning("bad GAMEACC frame: %s", e)
            return "protocol-error"
        if not isinstance(msg, GameAcc):
            return "protocol-error"
        if msg.accept != 0:
            return "rejected"

        board = Board()
        our_color_enum = Color.WHITE if our_color == "W" else Color.BLACK
        engine = AIEngine(difficulty=difficulty, color=our_color_enum, use_book=False, use_bitbase=False)
        turn: Color = Color.WHITE

        while True:
            go = board.check_game_over({}, quiet_plies=0, kings_only_plies=0)
            if go is not None:
                fh.write(encode(GameEnd(reason=0, stop=0)))
                return "ok"

            if turn == our_color_enum:
                t0 = time.perf_counter()
                ai_move = engine.find_move(board.copy())
                t1 = time.perf_counter()
                if ai_move is None:
                    fh.write(encode(GameEnd(reason=0, stop=0)))
                    return "ok"
                _apply_move_to_board(board, ai_move.path, ai_move.kind == "capture")
                fh.write(encode(_move_to_dxp(ai_move, t1 - t0)))
            else:
                frame = read_frame(fh)
                if not frame:
                    return "bye"
                try:
                    msg = decode(frame)
                except DXPProtocolError:
                    return "protocol-error"
                if isinstance(msg, GameEnd):
                    return "ok"
                if not isinstance(msg, Move):
                    return "protocol-error"
                path = _dxp_to_move_path(msg, board, turn)
                if path is None:
                    return "protocol-error"
                is_capture = bool(msg.captured) or len(path) > 2
                _apply_move_to_board(board, path, is_capture)

            turn = turn.opponent
