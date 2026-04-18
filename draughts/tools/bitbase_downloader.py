"""Bitbase downloader — implements D37.

Downloads the latest 4-piece endgame bitbase from GitHub Releases,
verifies its SHA256, and stores it in ``%APPDATA%/DRAUGHTS/bitbase/``
where load_default_bitbase() picks it up on the next engine startup.

This module is pure — no Qt imports. UI wiring lives in
draughts.ui.bitbase_downloader_dialog. Can also be invoked from the
CLI::

    python -m draughts.tools.bitbase_downloader --dest /path/to/bitbase/

Design notes:
- The release URL is configurable via the DRAUGHTS_BITBASE_URL env var,
  with a sensible default pointing to the project's GitHub Releases.
  This keeps the code release-agnostic: new versions just bump the URL.
- Downloads go to a temp file (``.download`` suffix), are SHA256-
  checked, then atomically renamed on success. A broken download
  never overwrites the existing file.
- Progress is reported via a callback ``on_progress(bytes_done,
  bytes_total)`` so UI can render a progress bar without this module
  depending on Qt.
- Cancellation: the caller can set a ``cancel_flag: list[bool]`` to
  ``[True]`` at any point; the chunked download checks it between
  chunks and raises ``BitbaseDownloadCancelled``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger("draughts.bitbase_downloader")

#: Default GitHub Releases URL for the 4-piece bitbase.
#: Override via the DRAUGHTS_BITBASE_URL env var or pass url= explicitly.
DEFAULT_BITBASE_URL = (
    "https://github.com/adugin/draughts/releases/latest/download/bitbase_4.json.gz"
)

#: Default SHA256 URL (.sha256 text file alongside the artifact).
DEFAULT_BITBASE_SHA256_URL = (
    "https://github.com/adugin/draughts/releases/latest/download/bitbase_4.json.gz.sha256"
)

#: Chunk size for streaming download — 256 KB keeps progress smooth
#: without burning RAM on small machines.
_CHUNK_SIZE = 256 * 1024


class BitbaseDownloadError(RuntimeError):
    """Base for bitbase downloader failures."""


class BitbaseDownloadCancelled(BitbaseDownloadError):
    """Raised when the caller set cancel_flag to [True] mid-download."""


class BitbaseChecksumMismatch(BitbaseDownloadError):
    """Raised when the downloaded file's SHA256 != advertised."""


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    size_bytes: int
    sha256: str


def get_destination_dir() -> Path:
    """Return (and create) the directory where downloaded bitbases live."""
    from draughts.config import get_data_dir

    dest = Path(get_data_dir()) / "bitbase"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def resolve_url(url: str | None = None) -> str:
    """Pick the effective download URL: arg > env > default."""
    if url:
        return url
    return os.environ.get("DRAUGHTS_BITBASE_URL", DEFAULT_BITBASE_URL)


def resolve_sha256_url(sha256_url: str | None = None) -> str:
    if sha256_url:
        return sha256_url
    return os.environ.get("DRAUGHTS_BITBASE_SHA256_URL", DEFAULT_BITBASE_SHA256_URL)


def _fetch_expected_sha256(sha256_url: str, timeout: float = 10.0) -> str | None:
    """Fetch the .sha256 text file; return the hex digest or None on failure."""
    try:
        with urllib.request.urlopen(sha256_url, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("ascii", errors="ignore").strip()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("SHA256 fetch failed from %s: %s", sha256_url, exc)
        return None
    # File may be "<hex>  filename\n" or just "<hex>"; take the first token.
    first = raw.split()[0] if raw else ""
    if len(first) == 64 and all(c in "0123456789abcdefABCDEF" for c in first):
        return first.lower()
    logger.warning("SHA256 file content malformed: %r", raw[:80])
    return None


def download_bitbase(
    url: str | None = None,
    dest_dir: Path | None = None,
    *,
    sha256_url: str | None = None,
    expected_sha256: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    cancel_flag: list[bool] | None = None,
    timeout: float = 30.0,
) -> DownloadResult:
    """Download the 4-piece bitbase with progress and integrity verification.

    Args:
        url: Source URL; defaults to GitHub Releases (see module docstring).
        dest_dir: Where to store the file; defaults to user data dir.
        sha256_url: URL of the .sha256 text file; skipped when
            ``expected_sha256`` is provided.
        expected_sha256: Pre-known hex digest to verify against. When
            None, we fetch ``sha256_url`` and use that. When both are
            None (or fetch fails), the download succeeds without
            verification but logs a warning.
        on_progress: Optional callback(bytes_done, bytes_total).
            bytes_total is 0 when the server omits Content-Length.
        cancel_flag: Optional [False/True] sentinel list — check between
            chunks; setting to [True] raises BitbaseDownloadCancelled.
        timeout: Socket timeout per connection.

    Returns:
        DownloadResult with the final path, size, and computed SHA256.

    Raises:
        BitbaseDownloadError on network / IO failure.
        BitbaseChecksumMismatch if expected_sha256 is set and differs.
        BitbaseDownloadCancelled if cancel_flag[0] becomes True.
    """
    effective_url = resolve_url(url)
    dest_dir = dest_dir or get_destination_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = effective_url.rsplit("/", 1)[-1] or "bitbase_4.json.gz"
    final_path = dest_dir / filename
    tmp_path = dest_dir / (filename + ".download")

    if expected_sha256 is None:
        expected_sha256 = _fetch_expected_sha256(resolve_sha256_url(sha256_url), timeout=timeout)

    sha = hashlib.sha256()
    bytes_done = 0

    try:
        with urllib.request.urlopen(effective_url, timeout=timeout) as resp:  # noqa: S310
            length_hdr = resp.headers.get("Content-Length")
            total = int(length_hdr) if length_hdr and length_hdr.isdigit() else 0

            with tmp_path.open("wb") as out:
                while True:
                    if cancel_flag is not None and cancel_flag and cancel_flag[0]:
                        raise BitbaseDownloadCancelled("user cancelled")
                    chunk = resp.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    out.write(chunk)
                    sha.update(chunk)
                    bytes_done += len(chunk)
                    if on_progress is not None:
                        on_progress(bytes_done, total)
    except BitbaseDownloadCancelled:
        tmp_path.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        tmp_path.unlink(missing_ok=True)
        raise BitbaseDownloadError(f"Download failed: {exc}") from exc

    actual = sha.hexdigest()
    if expected_sha256 and actual != expected_sha256:
        tmp_path.unlink(missing_ok=True)
        raise BitbaseChecksumMismatch(
            f"SHA256 mismatch: expected {expected_sha256}, got {actual}"
        )
    if expected_sha256 is None:
        logger.warning("No expected SHA256 available — accepting file unverified (%s)", actual)

    tmp_path.replace(final_path)  # atomic on POSIX + modern Windows
    return DownloadResult(path=final_path, size_bytes=bytes_done, sha256=actual)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Download the 4-piece bitbase.")
    parser.add_argument("--url", default=None, help="Download URL override")
    parser.add_argument("--sha256-url", default=None, help=".sha256 URL override")
    parser.add_argument("--expected-sha256", default=None, help="Pre-known SHA256 hex digest")
    parser.add_argument("--dest", default=None, type=Path, help="Output directory (default: user data dir)")
    args = parser.parse_args()

    def on_progress(done: int, total: int) -> None:
        if total:
            pct = 100.0 * done / total
            print(f"\r  {done / (1024 * 1024):.1f} / {total / (1024 * 1024):.1f} MB ({pct:.1f}%)", end="", file=sys.stderr)
        else:
            print(f"\r  {done / (1024 * 1024):.1f} MB", end="", file=sys.stderr)

    try:
        result = download_bitbase(
            url=args.url,
            dest_dir=args.dest,
            sha256_url=args.sha256_url,
            expected_sha256=args.expected_sha256,
            on_progress=on_progress,
        )
    except BitbaseDownloadError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    print(f"\nDownloaded: {result.path}\n  size: {result.size_bytes / (1024 * 1024):.1f} MB\n  sha256: {result.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
