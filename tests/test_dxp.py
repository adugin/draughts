"""Tests for DXP protocol codec (#33)."""

from __future__ import annotations

import io
import socket
import threading
import time

import pytest

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


# ---------------------------------------------------------------------------
# Codec roundtrip
# ---------------------------------------------------------------------------


def test_gamereq_roundtrip():
    m = GameReq(name="ENGINE-A", color="W", minutes=5, moves_to_end=40, setup="A")
    buf = encode(m)
    assert buf.endswith(b"\x00")
    m2 = decode(buf)
    assert isinstance(m2, GameReq)
    assert m2.name == "ENGINE-A"
    assert m2.color == "W"
    assert m2.minutes == 5
    assert m2.moves_to_end == 40
    assert m2.setup == "A"


def test_gameacc_accept_and_reject():
    accept = decode(encode(GameAcc(name="OURS", accept=0)))
    assert isinstance(accept, GameAcc)
    assert accept.accept == 0
    reject = decode(encode(GameAcc(name="OURS", accept=2)))
    assert isinstance(reject, GameAcc)
    assert reject.accept == 2


def test_move_no_captures():
    m = Move(time_centis=123, from_sq=22, to_sq=17, captured=[])
    m2 = decode(encode(m))
    assert isinstance(m2, Move)
    assert (m2.time_centis, m2.from_sq, m2.to_sq, m2.captured) == (123, 22, 17, [])


def test_move_with_captures():
    m = Move(time_centis=50, from_sq=9, to_sq=18, captured=[13])
    m2 = decode(encode(m))
    assert isinstance(m2, Move)
    assert m2.captured == [13]


def test_move_with_multi_captures():
    m = Move(time_centis=0, from_sq=9, to_sq=25, captured=[13, 22])
    m2 = decode(encode(m))
    assert isinstance(m2, Move)
    assert m2.captured == [13, 22]


def test_gameend_roundtrip():
    e = GameEnd(reason=1, stop=0)
    e2 = decode(encode(e))
    assert isinstance(e2, GameEnd)
    assert (e2.reason, e2.stop) == (1, 0)


def test_decode_unknown_code():
    with pytest.raises(DXPProtocolError):
        decode(b"Z000\x00")


def test_decode_empty():
    with pytest.raises(DXPProtocolError):
        decode(b"")


def test_decode_short_move():
    with pytest.raises(DXPProtocolError):
        decode(b"M00\x00")


def test_read_frame_consumes_until_null():
    buf = io.BytesIO(b"hello\x00world\x00")
    assert read_frame(buf) == b"hello\x00"
    assert read_frame(buf) == b"world\x00"
    assert read_frame(buf) == b""  # EOF


def test_read_frame_partial_returns_bytes_on_eof():
    buf = io.BytesIO(b"partial")
    data = read_frame(buf)
    # No NUL, hit EOF — return what we read (caller decides).
    assert data == b"partial"


# ---------------------------------------------------------------------------
# Server integration — one quick game at low depth
# ---------------------------------------------------------------------------


def _pick_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.slow
def test_server_accepts_gamereq_and_responds():
    """Smoke test: server responds GAMEACC to our GAMEREQ."""
    from draughts.engine.dxp_server import serve_forever

    port = _pick_free_port()
    thread = threading.Thread(
        target=serve_forever,
        kwargs={"port": port, "difficulty": 1, "max_games": 1},
        daemon=True,
    )
    thread.start()
    time.sleep(0.2)  # give server time to bind

    with socket.create_connection(("127.0.0.1", port), timeout=10.0) as sock:
        fh = sock.makefile("rwb", buffering=0)
        # Send GAMEREQ — initiator wants white, engine plays black.
        fh.write(encode(GameReq(name="TEST", color="W", minutes=1, moves_to_end=0, setup="A")))
        acc_frame = read_frame(fh)
        assert acc_frame, "expected GAMEACC response"
        acc = decode(acc_frame)
        assert isinstance(acc, GameAcc)
        assert acc.accept == 0

        # Send GAMEEND to finish cleanly — don't want to play 30+ moves
        # in a unit test.
        fh.write(encode(GameEnd(reason=1, stop=0)))

    thread.join(timeout=20.0)
    assert not thread.is_alive(), "server should have exited after max_games=1"
