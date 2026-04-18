"""Tests for the bitbase downloader (D37)."""

from __future__ import annotations

import hashlib
import http.server
import socketserver
import threading
from pathlib import Path

import pytest

from draughts.tools.bitbase_downloader import (
    BitbaseChecksumMismatch,
    BitbaseDownloadCancelled,
    BitbaseDownloadError,
    BitbaseInsecureURL,
    BitbaseIntegrityUnavailable,
    BitbaseSizeExceeded,
    download_bitbase,
    resolve_url,
)


def _pick_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def local_http_server(tmp_path: Path):
    """Serve tmp_path via http.server on a random port — teardown on exit."""
    port = _pick_port()
    handler = http.server.SimpleHTTPRequestHandler
    handler.directory = str(tmp_path)

    class _Handler(handler):  # type: ignore[valid-type,misc]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(tmp_path), **kwargs)

        def log_message(self, *_args, **_kwargs):  # noqa: N802
            pass

    srv = socketserver.TCPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", tmp_path
    finally:
        srv.shutdown()
        srv.server_close()


# ---------------------------------------------------------------------------
# resolve_url
# ---------------------------------------------------------------------------


def test_resolve_url_from_arg():
    assert resolve_url("https://example.com/foo.gz") == "https://example.com/foo.gz"


def test_resolve_url_from_env(monkeypatch):
    monkeypatch.setenv("DRAUGHTS_BITBASE_URL", "https://env.example/bar.gz")
    assert resolve_url(None) == "https://env.example/bar.gz"


def test_resolve_url_default(monkeypatch):
    monkeypatch.delenv("DRAUGHTS_BITBASE_URL", raising=False)
    assert resolve_url(None).startswith("https://")


# ---------------------------------------------------------------------------
# download_bitbase — happy path
# ---------------------------------------------------------------------------


def test_download_with_correct_sha256(local_http_server, tmp_path: Path):
    base_url, serve_dir = local_http_server
    payload = b"fake-bitbase-contents" * 100
    (serve_dir / "bitbase_4.json.gz").write_bytes(payload)
    expected_sha = hashlib.sha256(payload).hexdigest()

    dest = tmp_path / "dest"
    result = download_bitbase(
        url=f"{base_url}/bitbase_4.json.gz",
        dest_dir=dest,
        expected_sha256=expected_sha,
        allow_http=True,
    )
    assert result.path == dest / "bitbase_4.json.gz"
    assert result.path.read_bytes() == payload
    assert result.size_bytes == len(payload)
    assert result.sha256 == expected_sha


def test_download_progress_callback_called(local_http_server, tmp_path: Path):
    base_url, serve_dir = local_http_server
    payload = b"x" * (300 * 1024)  # > 1 chunk at 256 KB
    (serve_dir / "f.gz").write_bytes(payload)

    progress_calls: list[tuple[int, int]] = []
    download_bitbase(
        url=f"{base_url}/f.gz",
        dest_dir=tmp_path / "dest",
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        on_progress=lambda done, total: progress_calls.append((done, total)),
        allow_http=True,
    )
    assert progress_calls
    assert progress_calls[-1][0] == len(payload)


# ---------------------------------------------------------------------------
# Verification failures
# ---------------------------------------------------------------------------


def test_checksum_mismatch_raises_and_cleans_up(local_http_server, tmp_path: Path):
    base_url, serve_dir = local_http_server
    (serve_dir / "f.gz").write_bytes(b"actual contents")

    dest = tmp_path / "dest"
    with pytest.raises(BitbaseChecksumMismatch):
        download_bitbase(
            url=f"{base_url}/f.gz",
            dest_dir=dest,
            expected_sha256="0" * 64,  # bogus
            allow_http=True,
        )
    # No partial file left behind.
    assert not (dest / "f.gz").exists()
    assert not (dest / "f.gz.download").exists()


def test_network_error_raises(tmp_path: Path):
    # localhost on an unused port → connection refused
    with pytest.raises(BitbaseDownloadError):
        download_bitbase(
            url="http://127.0.0.1:1/nonexistent.gz",
            dest_dir=tmp_path / "dest",
            expected_sha256="0" * 64,  # bypass integrity fetch
            allow_http=True,
        )


# ---------------------------------------------------------------------------
# Audit fixes (HIGH-02, HIGH-03, HIGH-07)
# ---------------------------------------------------------------------------


def test_http_scheme_refused_by_default(tmp_path: Path):
    """HIGH-07: plain http:// URL must be rejected unless opted in."""
    with pytest.raises(BitbaseInsecureURL):
        download_bitbase(
            url="http://example.com/file.gz",
            dest_dir=tmp_path / "dest",
            expected_sha256="0" * 64,
        )


def test_allow_http_bypasses_scheme_check(local_http_server, tmp_path: Path):
    """allow_http=True path works (used by the local test server)."""
    base_url, serve_dir = local_http_server
    payload = b"hello"
    (serve_dir / "f.gz").write_bytes(payload)

    result = download_bitbase(
        url=f"{base_url}/f.gz",
        dest_dir=tmp_path / "dest",
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        allow_http=True,
    )
    assert result.size_bytes == len(payload)


def test_missing_sha256_rejects_by_default(local_http_server, tmp_path: Path):
    """HIGH-02: no .sha256 sibling → BitbaseIntegrityUnavailable."""
    base_url, serve_dir = local_http_server
    (serve_dir / "f.gz").write_bytes(b"x" * 100)
    # No .sha256 file served; caller provides neither expected nor url.
    with pytest.raises(BitbaseIntegrityUnavailable):
        download_bitbase(
            url=f"{base_url}/f.gz",
            dest_dir=tmp_path / "dest",
            sha256_url=f"{base_url}/nonexistent.sha256",
            allow_http=True,
        )


def test_allow_unverified_accepts_missing_sha(local_http_server, tmp_path: Path):
    """allow_unverified=True explicitly opts out of integrity."""
    base_url, serve_dir = local_http_server
    (serve_dir / "f.gz").write_bytes(b"y" * 100)
    result = download_bitbase(
        url=f"{base_url}/f.gz",
        dest_dir=tmp_path / "dest",
        sha256_url=f"{base_url}/nonexistent.sha256",
        allow_http=True,
        allow_unverified=True,
    )
    assert (tmp_path / "dest" / "f.gz").exists()
    assert result.size_bytes == 100


def test_size_cap_rejects_large_payload(local_http_server, tmp_path: Path):
    """HIGH-03: max_bytes cap short-circuits the stream."""
    base_url, serve_dir = local_http_server
    payload = b"Z" * (500 * 1024)  # 500 KB
    (serve_dir / "big.gz").write_bytes(payload)

    with pytest.raises(BitbaseSizeExceeded):
        download_bitbase(
            url=f"{base_url}/big.gz",
            dest_dir=tmp_path / "dest",
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            allow_http=True,
            max_bytes=100 * 1024,  # 100 KB cap
        )
    # Tmp file cleaned up.
    assert not (tmp_path / "dest" / "big.gz.download").exists()
    assert not (tmp_path / "dest" / "big.gz").exists()


# ---------------------------------------------------------------------------
# Integration: downloader → load_default_bitbase picks up the new file
# ---------------------------------------------------------------------------


def test_downloaded_file_is_picked_up_by_loader(
    local_http_server, tmp_path: Path, monkeypatch
):
    """Closes the loop: download a valid bitbase, call load_default_bitbase,
    verify the engine now uses it. Guards BLK-02 / user_data path wiring.
    """
    import json

    from draughts.game.ai.bitbase import DRAW, EndgameBitbase, WIN
    from draughts.game.ai.tt import _zobrist_hash
    from draughts.game.board import Board
    from draughts.config import Color

    # Build a realistic bitbase payload (JSON of int-string keys).
    bb = EndgameBitbase(entries={1: WIN, 2: DRAW}, max_pieces=4)
    out_path = tmp_path / "source" / "bitbase_4.json"
    out_path.parent.mkdir()
    bb.save(out_path)
    payload = out_path.read_bytes()

    base_url, serve_dir = local_http_server
    (serve_dir / "bitbase_4.json").write_bytes(payload)

    # Point user_data.bitbase_dir() at a scratch path and download there.
    fake_user_dir = tmp_path / "user_bitbase"
    monkeypatch.setattr("draughts.user_data.bitbase_dir", lambda: fake_user_dir)

    result = download_bitbase(
        url=f"{base_url}/bitbase_4.json",
        dest_dir=fake_user_dir,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        allow_http=True,
    )
    assert result.path.exists()

    # load_default_bitbase probes user dir first.
    from draughts.game.ai import load_default_bitbase

    bb_loaded = load_default_bitbase()
    assert bb_loaded is not None
    assert bb_loaded.max_pieces == 4
    # Both entries present.
    assert bb_loaded.probe_hash(1) == WIN
    assert bb_loaded.probe_hash(2) == DRAW

    # Cleanup: restore shipped bitbase for subsequent tests.
    monkeypatch.undo()
    load_default_bitbase()


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_cancel_flag_interrupts(local_http_server, tmp_path: Path):
    base_url, serve_dir = local_http_server
    payload = b"y" * (2 * 1024 * 1024)  # 2 MB — guarantees multi-chunk
    (serve_dir / "big.gz").write_bytes(payload)

    cancel = [False]

    def on_progress(done: int, total: int) -> None:
        if done > 128 * 1024:  # after 128 KB, ask for cancel
            cancel[0] = True

    with pytest.raises(BitbaseDownloadCancelled):
        download_bitbase(
            url=f"{base_url}/big.gz",
            dest_dir=tmp_path / "dest",
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            on_progress=on_progress,
            cancel_flag=cancel,
            allow_http=True,
        )
    # Tmp file cleaned up; final file not created.
    assert not (tmp_path / "dest" / "big.gz").exists()
    assert not (tmp_path / "dest" / "big.gz.download").exists()


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


def test_existing_file_preserved_if_download_fails(local_http_server, tmp_path: Path):
    base_url, serve_dir = local_http_server
    (serve_dir / "f.gz").write_bytes(b"new contents")

    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "f.gz").write_bytes(b"old contents")

    with pytest.raises(BitbaseChecksumMismatch):
        download_bitbase(
            url=f"{base_url}/f.gz",
            dest_dir=dest,
            expected_sha256="0" * 64,
            allow_http=True,
        )
    # Old file untouched — atomic rename only happens on success.
    assert (dest / "f.gz").read_bytes() == b"old contents"
