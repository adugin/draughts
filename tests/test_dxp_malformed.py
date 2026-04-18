"""DXP decode hardening — adversarial frames must raise DXPProtocolError.

Before hardening, a hostile or truncated frame could raise IndexError,
ValueError, or UnicodeDecodeError — none caught by the server/client
loops that only handle ``DXPProtocolError``. The worker thread would
die silently, leaving the socket half-open and the main loop stuck on
``accept()`` without a clear diagnostic.

Every test here asserts that the specific malformed input surfaces as
``DXPProtocolError`` (and nothing else), so the surrounding
``except DXPProtocolError:`` handlers in ``dxp_server.py`` /
``dxp_client.py`` correctly terminate the session.
"""

from __future__ import annotations

import io

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
# Frame envelope
# ---------------------------------------------------------------------------


def test_decode_null_only_frame():
    """``\\x00`` alone leaves an empty body — must not IndexError."""
    with pytest.raises(DXPProtocolError):
        decode(b"\x00")


def test_decode_non_ascii_byte():
    """High-bit bytes must surface as DXPProtocolError, not UnicodeDecodeError."""
    with pytest.raises(DXPProtocolError):
        decode(b"R\xff000\x00")


# ---------------------------------------------------------------------------
# GAMEREQ edge cases
# ---------------------------------------------------------------------------


def test_gamereq_non_digit_minutes():
    """Non-digit in the minutes field must raise DXPProtocolError, not ValueError."""
    # Build a GAMEREQ-shaped frame with letters where digits must go.
    body = b"R" + b"1" + b" " * 32 + b"W" + b"abc" + b"000" + b"A" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


def test_gamereq_non_digit_moves_to_end():
    body = b"R" + b"1" + b" " * 32 + b"W" + b"005" + b"xyz" + b"A" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


def test_gamereq_invalid_color_letter():
    """Color must be 'W' or 'B' — reject 'X', 'w', digits, etc."""
    body = b"R" + b"1" + b" " * 32 + b"X" + b"005" + b"000" + b"A" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


def test_gamereq_invalid_setup_letter():
    body = b"R" + b"1" + b" " * 32 + b"W" + b"005" + b"000" + b"Q" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


def test_gamereq_truncated_one_byte():
    """Only 'R' — no header length — must raise DXPProtocolError, not IndexError."""
    with pytest.raises(DXPProtocolError):
        decode(b"R\x00")


def test_gamereq_truncated_mid_header():
    """Valid prefix but cut before the setup byte."""
    body = b"R" + b"1" + b" " * 32 + b"W" + b"005" + b"000" + b"\x00"  # missing setup
    with pytest.raises(DXPProtocolError):
        decode(body)


# ---------------------------------------------------------------------------
# GAMEACC edge cases
# ---------------------------------------------------------------------------


def test_gameacc_non_digit_accept():
    body = b"A" + b" " * 32 + b"Z" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


def test_gameacc_truncated():
    """Only 'A' + short name — no accept byte."""
    with pytest.raises(DXPProtocolError):
        decode(b"A" + b" " * 32 + b"\x00")


# ---------------------------------------------------------------------------
# MOVE edge cases
# ---------------------------------------------------------------------------


def test_move_non_digit_from_sq():
    body = b"M" + b"0000" + b"ab" + b"15" + b"00" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


def test_move_non_digit_ncap():
    body = b"M" + b"0000" + b"22" + b"15" + b"XX" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


def test_move_absurd_ncap_rejected():
    """99 captures is physically impossible — peer is either malicious or buggy."""
    # Claim 99 captures but don't bother appending 198 digits — the
    # implausible count is rejected before we try to parse the body.
    body = b"M" + b"0000" + b"22" + b"15" + b"99" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


def test_move_captures_truncated():
    """n_cap=2 but only one capture square present."""
    body = b"M" + b"0000" + b"09" + b"25" + b"02" + b"13" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


def test_move_non_digit_captured_square():
    body = b"M" + b"0000" + b"09" + b"25" + b"01" + b"XX" + b"\x00"
    with pytest.raises(DXPProtocolError):
        decode(body)


# ---------------------------------------------------------------------------
# GAMEEND edge cases
# ---------------------------------------------------------------------------


def test_gameend_non_digit_reason():
    with pytest.raises(DXPProtocolError):
        decode(b"EX0\x00")


def test_gameend_non_digit_stop():
    with pytest.raises(DXPProtocolError):
        decode(b"E0X\x00")


def test_gameend_truncated():
    with pytest.raises(DXPProtocolError):
        decode(b"E0\x00")  # only reason, no stop


# ---------------------------------------------------------------------------
# Regression: well-formed frames still round-trip
# ---------------------------------------------------------------------------


def test_gamereq_b_color_still_accepted():
    """'B' is a valid color (initiator wants black)."""
    msg = decode(encode(GameReq(color="B")))
    assert isinstance(msg, GameReq)
    assert msg.color == "B"


def test_gamereq_setup_s_still_accepted():
    """'S' (setup-follows) is protocol-valid even if we don't decode the FEN."""
    msg = decode(encode(GameReq(setup="S")))
    assert isinstance(msg, GameReq)
    assert msg.setup == "S"


def test_move_max_captures_accepted():
    """Captures up to _MAX_CAPTURED must round-trip cleanly."""
    from draughts.engine.dxp import _MAX_CAPTURED

    squares = list(range(1, _MAX_CAPTURED + 1))
    m = Move(time_centis=0, from_sq=1, to_sq=32, captured=squares)
    m2 = decode(encode(m))
    assert isinstance(m2, Move)
    assert m2.captured == squares


# ---------------------------------------------------------------------------
# End-to-end: server-style loop must recover on hostile input
# ---------------------------------------------------------------------------


def test_partial_frame_then_decode_raises():
    """Truncated-at-EOF GAMEREQ parsed by the server loop returns DXPProtocolError
    (which the server handler maps to 'protocol-error'), not a crash."""
    # read_frame returns the (short) buffer on EOF; decode must reject it.
    truncated = b"R1" + b" " * 10  # way too short, no NUL
    buf = io.BytesIO(truncated)
    frame = read_frame(buf)
    assert frame == truncated
    with pytest.raises(DXPProtocolError):
        decode(frame)
