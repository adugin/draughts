"""Minimal DXP server — plays one game per incoming TCP connection.

Listens on a port (default 27531), expects a GAMEREQ, replies GAMEACC,
then alternates MOVE messages until GAMEEND.  The engine plays the
color OPPOSITE of the initiator's request (if initiator wants white,
server plays black, and vice versa).

Only one game per connection. Concurrency: accept() loop serves one
client at a time — good enough for the "10-game self-match" acceptance
criterion and avoids thread/async complexity.

Square numbering follows Russian-draughts 1-32 convention via the
pdn.square_to_xy / xy_to_square helpers.
"""

from __future__ import annotations

import logging
import socket
import time
from typing import Optional

from draughts.config import Color
from draughts.engine.dxp import (
    DXPProtocolError,
    GameAcc,
    GameEnd,
    GameReq,
    Move,
    decode,
    encode,
    read_frame,
)
from draughts.game.ai import AIEngine, AIMove
from draughts.game.board import Board
from draughts.game.pdn import square_to_xy, xy_to_square

logger = logging.getLogger("draughts.dxp.server")


DEFAULT_PORT = 27531


def _move_to_dxp(move: AIMove, time_used: float) -> Move:
    """Convert our AIMove into a DXP Move frame."""
    start_x, start_y = move.path[0]
    end_x, end_y = move.path[-1]
    from_sq = xy_to_square(start_x, start_y)
    to_sq = xy_to_square(end_x, end_y)
    captured: list[int] = []
    if move.kind == "capture":
        # Intermediate squares along the capture path are jumped-over
        # enemy pieces' squares for DXP purposes. We approximate with the
        # intermediate path squares; many GUIs accept either the enemy
        # squares or the landing squares.
        for ix, iy in move.path[1:-1]:
            captured.append(xy_to_square(ix, iy))
    return Move(
        time_centis=max(0, int(time_used * 100)),
        from_sq=from_sq,
        to_sq=to_sq,
        captured=captured,
    )


def _dxp_to_move_path(m: Move, board: Board, color: Color) -> list[tuple[int, int]] | None:
    """Find our internal move path matching the DXP from/to squares.

    HIGH-05 fix: when multiple legal moves share the same from/to
    (possible for flying kings in multi-capture), disambiguate via the
    captured-squares list. Returns None if:
      - no legal move matches from/to (peer sent an illegal move), OR
      - multiple matches remain and captured list cannot disambiguate
        (we'd rather abort than silently desync).
    """
    from draughts.game.ai import _generate_all_moves

    candidates = _generate_all_moves(board, color)
    try:
        fx, fy = square_to_xy(m.from_sq)
        tx, ty = square_to_xy(m.to_sq)
    except ValueError:
        return None
    endpoint_matches = [
        (kind, path) for kind, path in candidates
        if path[0] == (fx, fy) and path[-1] == (tx, ty)
    ]
    if not endpoint_matches:
        return None
    if len(endpoint_matches) == 1:
        return endpoint_matches[0][1]

    # Multiple paths share endpoints — use captured squares from peer.
    if not m.captured:
        logger.warning(
            "Ambiguous move %d→%d (%d candidates) and peer sent no "
            "captured-list — cannot disambiguate",
            m.from_sq, m.to_sq, len(endpoint_matches),
        )
        return None

    expected_captures = set(m.captured)
    for _kind, path in endpoint_matches:
        # Interim squares of a capture path are jumped-landing squares
        # from our side; enemy-piece squares are the intermediates.
        # For ambiguity resolution we check if the set of intermediate
        # landing squares' xy → square-number equals the peer-supplied list.
        path_interim_squares = set()
        for ix, iy in path[1:-1]:
            try:
                path_interim_squares.add(xy_to_square(ix, iy))
            except ValueError:
                continue
        if path_interim_squares == expected_captures:
            return path

    logger.warning(
        "Ambiguous move %d→%d and captured-list %s did not match any path",
        m.from_sq, m.to_sq, sorted(m.captured),
    )
    return None


def _apply_move_to_board(board: Board, path: list[tuple[int, int]], is_capture: bool) -> None:
    if is_capture:
        board.execute_capture_path(path)
    else:
        (x1, y1), (x2, y2) = path[0], path[1]
        board.execute_move(x1, y1, x2, y2)


def play_one_game(sock: socket.socket, *, difficulty: int = 4, our_name: str = "DRAUGHTS") -> str:
    """Full DXP handshake + game loop on a connected socket.

    Returns a short status string for logging: "ok", "rejected",
    "timeout", "protocol-error", "bye".
    """
    sock.settimeout(60.0)
    fh = sock.makefile("rwb", buffering=0)

    # 1. Expect GAMEREQ
    frame = read_frame(fh)
    if not frame:
        return "bye"
    try:
        msg = decode(frame)
    except DXPProtocolError as e:
        logger.warning("bad first frame: %s", e)
        return "protocol-error"
    if not isinstance(msg, GameReq):
        logger.warning("expected GAMEREQ, got %r", type(msg).__name__)
        return "protocol-error"

    initiator = msg
    logger.info(
        "GAMEREQ from %r, wants %s, %d min, %d moves-to-end",
        initiator.name, initiator.color, initiator.minutes, initiator.moves_to_end,
    )

    # 2. Send GAMEACC (always accept for now).
    fh.write(encode(GameAcc(name=our_name, accept=0)))

    # 3. Decide colors.
    board = Board()
    initiator_color = Color.WHITE if initiator.color == "W" else Color.BLACK
    our_color = initiator_color.opponent
    engine = AIEngine(difficulty=difficulty, color=our_color, use_book=False, use_bitbase=False)
    turn: Color = Color.WHITE

    # HIGH-04 fix: derive per-move budget from GAMEREQ clock so we
    # respect the initiator's requested time control. Assume ~40 moves
    # per game (typical for Russian draughts). minutes=0 means "no
    # clock" — fall back to engine's default fixed-depth search.
    if initiator.minutes > 0:
        total_budget_ms = initiator.minutes * 60 * 1000
        assumed_moves = max(10, initiator.moves_to_end or 40)
        per_move_ms = max(100, total_budget_ms // assumed_moves)
    else:
        per_move_ms = 0  # fall through to find_move (depth-based)

    # 4. Game loop. White moves first always in Russian draughts.
    while True:
        # Check game over before asking for a move.
        go = board.check_game_over({}, quiet_plies=0, kings_only_plies=0)
        if go is not None:
            fh.write(encode(GameEnd(reason=0, stop=0)))
            return "ok"

        if turn == our_color:
            t0 = time.perf_counter()
            if per_move_ms > 0 and hasattr(engine, "find_move_timed"):
                ai_move = engine.find_move_timed(board.copy(), time_ms=per_move_ms)
            else:
                ai_move = engine.find_move(board.copy())
            t1 = time.perf_counter()
            if ai_move is None:
                fh.write(encode(GameEnd(reason=0, stop=0)))
                return "ok"
            _apply_move_to_board(board, ai_move.path, ai_move.kind == "capture")
            dxp_move = _move_to_dxp(ai_move, t1 - t0)
            fh.write(encode(dxp_move))
        else:
            frame = read_frame(fh)
            if not frame:
                return "bye"
            try:
                msg = decode(frame)
            except DXPProtocolError as e:
                logger.warning("bad frame: %s", e)
                return "protocol-error"
            if isinstance(msg, GameEnd):
                return "ok"
            if not isinstance(msg, Move):
                logger.warning("expected MOVE, got %r", type(msg).__name__)
                return "protocol-error"
            path = _dxp_to_move_path(msg, board, turn)
            if path is None:
                logger.warning("peer sent illegal move: %r", msg)
                fh.write(encode(GameEnd(reason=1, stop=0)))
                return "protocol-error"
            # Heuristic: capture if intermediate squares were provided, or if
            # the move gives mandatory captures currently.
            is_capture = bool(msg.captured) or len(path) > 2
            _apply_move_to_board(board, path, is_capture)

        turn = turn.opponent


def serve_forever(
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    *,
    difficulty: int = 4,
    max_games: Optional[int] = None,
) -> None:
    """Accept games sequentially until max_games (None = forever)."""
    games_played = 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(1)
        logger.info("DXP server listening on %s:%d", host, port)
        while max_games is None or games_played < max_games:
            conn, addr = srv.accept()
            logger.info("connection from %s", addr)
            with conn:
                status = play_one_game(conn, difficulty=difficulty)
                logger.info("game ended: %s", status)
            games_played += 1
