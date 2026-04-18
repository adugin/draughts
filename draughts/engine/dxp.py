"""DXP (Draughts eXchange Protocol) message codec.

Implements the subset of DXP sufficient for engine-vs-engine play:
GAMEREQ, GAMEACC, MOVE, GAMEEND. Chat/back-request are omitted — they
are optional for a minimal playable server.

Reference (FMJD DXP v1.0):
    R — GAMEREQ  : R + V(1) + NAME(32) + C(1) + T(3) + M(3) + S(1)
    A — GAMEACC  : A + NAME(32) + K(1)
    M — MOVE     : M + T(4) + F(2) + TO(2) + N(2) + captured(2*N)
    E — GAMEEND  : E + R(1) + K(1)

Each message is NUL-terminated (\\x00).  All numeric fields are fixed-
width zero-padded decimal ASCII. Squares use 2-digit international
notation. Name fields are right-padded with spaces to 32 chars.

This codec is pure — no sockets. See dxp_server.py for the TCP loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field


PROTOCOL_VERSION = "1"
NULL = b"\x00"

#: Maximum legal DXP frame size in bytes. Real frames are < 200 bytes
#: (GAMEREQ is ~42, MOVE with 8 captures is ~31). Cap at 4 KB to reject
#: malicious / malformed input that would exhaust memory via read_frame
#: (HIGH-03 fix).
MAX_FRAME_BYTES = 4096


@dataclass
class GameReq:
    """GAMEREQ — initiator requests a new game."""

    name: str = "DRAUGHTS"
    # Side the INITIATOR wants to play. "W" or "B".
    color: str = "W"
    minutes: int = 5
    moves_to_end: int = 0
    # "A" = startpos, "S" = SetUp follows (FEN-ish field), not used here.
    setup: str = "A"


@dataclass
class GameAcc:
    """GAMEACC — reply to a GAMEREQ."""

    name: str = "DRAUGHTS"
    accept: int = 0  # 0 = accept, non-zero = error code (1=unsupported, 2=too short time, etc.)


@dataclass
class Move:
    """MOVE — one ply played by the sender."""

    time_centis: int = 0  # time used, in 1/100 seconds
    from_sq: int = 0
    to_sq: int = 0
    captured: list[int] = field(default_factory=list)


@dataclass
class GameEnd:
    """GAMEEND — game terminated."""

    reason: int = 0  # 0 = normal end, 1 = resign, 2 = draw offer accepted
    stop: int = 0  # confirmation flag


DXPMessage = GameReq | GameAcc | Move | GameEnd


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------


def _name_field(name: str) -> str:
    return (name[:32]).ljust(32)


def encode(msg: DXPMessage) -> bytes:
    """Serialize a DXP message (including trailing NUL)."""
    if isinstance(msg, GameReq):
        body = (
            "R"
            + PROTOCOL_VERSION
            + _name_field(msg.name)
            + msg.color
            + f"{msg.minutes:03d}"
            + f"{msg.moves_to_end:03d}"
            + msg.setup
        )
    elif isinstance(msg, GameAcc):
        body = "A" + _name_field(msg.name) + f"{msg.accept:1d}"
    elif isinstance(msg, Move):
        body = (
            "M"
            + f"{msg.time_centis:04d}"
            + f"{msg.from_sq:02d}"
            + f"{msg.to_sq:02d}"
            + f"{len(msg.captured):02d}"
            + "".join(f"{sq:02d}" for sq in msg.captured)
        )
    elif isinstance(msg, GameEnd):
        body = "E" + f"{msg.reason:1d}" + f"{msg.stop:1d}"
    else:
        raise TypeError(f"Unknown DXP message type: {type(msg).__name__}")

    return body.encode("ascii") + NULL


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------


class DXPProtocolError(ValueError):
    """Raised when a DXP frame cannot be parsed."""


def decode(frame: bytes) -> DXPMessage:
    """Parse a single DXP frame (trailing NUL optional)."""
    if not frame:
        raise DXPProtocolError("empty frame")
    if frame.endswith(NULL):
        frame = frame[:-1]
    text = frame.decode("ascii")

    code = text[0]
    if code == "R":
        if len(text) < 1 + 1 + 32 + 1 + 3 + 3 + 1:
            raise DXPProtocolError(f"short GAMEREQ: {text!r}")
        _version = text[1]
        name = text[2:34].rstrip()
        color = text[34]
        minutes = int(text[35:38])
        moves_to_end = int(text[38:41])
        setup = text[41]
        return GameReq(name=name, color=color, minutes=minutes, moves_to_end=moves_to_end, setup=setup)

    if code == "A":
        if len(text) < 1 + 32 + 1:
            raise DXPProtocolError(f"short GAMEACC: {text!r}")
        name = text[1:33].rstrip()
        accept = int(text[33])
        return GameAcc(name=name, accept=accept)

    if code == "M":
        if len(text) < 1 + 4 + 2 + 2 + 2:
            raise DXPProtocolError(f"short MOVE: {text!r}")
        time_centis = int(text[1:5])
        from_sq = int(text[5:7])
        to_sq = int(text[7:9])
        n_cap = int(text[9:11])
        expected_len = 11 + 2 * n_cap
        if len(text) < expected_len:
            raise DXPProtocolError(f"MOVE captures truncated: {text!r}")
        captured = [int(text[11 + 2 * i : 13 + 2 * i]) for i in range(n_cap)]
        return Move(time_centis=time_centis, from_sq=from_sq, to_sq=to_sq, captured=captured)

    if code == "E":
        if len(text) < 3:
            raise DXPProtocolError(f"short GAMEEND: {text!r}")
        reason = int(text[1])
        stop = int(text[2])
        return GameEnd(reason=reason, stop=stop)

    raise DXPProtocolError(f"unknown message code {code!r}: {text!r}")


def read_frame(readable, max_bytes: int = MAX_FRAME_BYTES) -> bytes:
    """Read one NUL-terminated frame from a byte-oriented source.

    ``readable`` must support ``read(n)`` returning bytes (a socket.makefile
    object or BufferedReader works).  Returns the frame INCLUDING the NUL,
    or an empty bytes object on EOF.

    HIGH-03 fix: enforces ``max_bytes`` ceiling. A malicious peer that
    never sends a NUL cannot exhaust server memory — we raise
    DXPProtocolError once the cap is reached.
    """
    buf = bytearray()
    while True:
        b = readable.read(1)
        if not b:
            return bytes(buf)  # EOF — may be partial; caller decides
        buf.extend(b)
        if b == NULL:
            return bytes(buf)
        if len(buf) > max_bytes:
            raise DXPProtocolError(
                f"Frame exceeded {max_bytes} bytes without NUL terminator — "
                "refusing to buffer more (possible DoS)"
            )
