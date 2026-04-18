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
            expected_sha256=None,
            sha256_url="http://127.0.0.1:1/nope.sha256",
        )


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
        )
    # Old file untouched — atomic rename only happens on success.
    assert (dest / "f.gz").read_bytes() == b"old contents"
