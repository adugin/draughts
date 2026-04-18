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

#: Hard size ceiling. 4-piece bitbase is ~126 MB; anything >1 GB is
#: almost certainly a mirror/MITM mistake. User override via
#: ``max_bytes`` arg. (HIGH-03 fix)
_DEFAULT_MAX_BYTES = 1024 * 1024 * 1024  # 1 GB


class BitbaseDownloadError(RuntimeError):
    """Base for bitbase downloader failures."""


class BitbaseDownloadCancelled(BitbaseDownloadError):
    """Raised when the caller set cancel_flag to [True] mid-download."""


class BitbaseChecksumMismatch(BitbaseDownloadError):
    """Raised when the downloaded file's SHA256 != advertised."""


class BitbaseIntegrityUnavailable(BitbaseDownloadError):
    """Raised when the .sha256 file cannot be retrieved and the caller
    required integrity verification (HIGH-02 fix: integrity is ON by
    default; allow_unverified=True opts out)."""


class BitbaseSizeExceeded(BitbaseDownloadError):
    """Raised when the payload exceeds max_bytes (HIGH-03 fix)."""


class BitbaseInsecureURL(BitbaseDownloadError):
    """Raised when a non-https URL is used without the allow_http escape hatch
    (HIGH-07 fix)."""


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


def _validate_url_scheme(url: str, *, allow_http: bool) -> None:
    """Raise BitbaseInsecureURL if url is non-https and allow_http=False."""
    scheme = url.split(":", 1)[0].lower()
    if scheme == "https":
        return
    if scheme == "http" and allow_http:
        logger.warning("Insecure HTTP download allowed via allow_http=True (%s)", url)
        return
    raise BitbaseInsecureURL(
        f"Refusing to download from {scheme!r} URL. "
        "Pass allow_http=True or set DRAUGHTS_ALLOW_HTTP=1 for local testing."
    )


def download_bitbase(
    url: str | None = None,
    dest_dir: Path | None = None,
    *,
    sha256_url: str | None = None,
    expected_sha256: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    cancel_flag: list[bool] | None = None,
    timeout: float = 30.0,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    allow_unverified: bool = False,
    allow_http: bool | None = None,
) -> DownloadResult:
    """Download the 4-piece bitbase with progress, size cap, and integrity.

    Safety contract (post-audit):
      - **HTTPS only** unless ``allow_http=True`` or env DRAUGHTS_ALLOW_HTTP=1 (HIGH-07).
      - **Integrity required** — fetches ``sha256_url`` or uses ``expected_sha256``;
        raises BitbaseIntegrityUnavailable if neither is available and
        ``allow_unverified`` is False (HIGH-02).
      - **Size cap** — abort if payload > ``max_bytes`` (default 1 GB) (HIGH-03).

    Args:
        url: Source URL; defaults to the GitHub Releases URL.
        dest_dir: Where to store the file; defaults to user data dir.
        sha256_url: URL of the .sha256 sibling.
        expected_sha256: Pre-known hex digest (overrides sha256_url fetch).
        on_progress: Callback(bytes_done, bytes_total).
        cancel_flag: [False/True] sentinel; set to [True] to interrupt.
        timeout: Socket timeout per connection.
        max_bytes: Reject downloads larger than this (default 1 GB).
        allow_unverified: Opt in to downloads without SHA256 verification.
        allow_http: Override the HTTPS-only default. None → check env.

    Raises:
        BitbaseInsecureURL — URL is not https and allow_http is off.
        BitbaseIntegrityUnavailable — no .sha256 and allow_unverified=False.
        BitbaseSizeExceeded — payload > max_bytes.
        BitbaseChecksumMismatch — hash differs from expected.
        BitbaseDownloadCancelled — cancel_flag[0] became True.
        BitbaseDownloadError — other network / IO failure.
    """
    import os as _os

    effective_url = resolve_url(url)
    if allow_http is None:
        allow_http = _os.environ.get("DRAUGHTS_ALLOW_HTTP") == "1"
    _validate_url_scheme(effective_url, allow_http=allow_http)

    dest_dir = dest_dir or get_destination_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = effective_url.rsplit("/", 1)[-1] or "bitbase_4.json.gz"
    final_path = dest_dir / filename
    tmp_path = dest_dir / (filename + ".download")

    if expected_sha256 is None:
        sha_url = resolve_sha256_url(sha256_url)
        if allow_http or sha_url.startswith("https://"):
            expected_sha256 = _fetch_expected_sha256(sha_url, timeout=timeout)

    if expected_sha256 is None and not allow_unverified:
        raise BitbaseIntegrityUnavailable(
            "Cannot verify file integrity: no expected SHA-256 available. "
            "The download was refused. Pass allow_unverified=True to override "
            "or ensure the .sha256 sibling file is published."
        )

    sha = hashlib.sha256()
    bytes_done = 0

    try:
        with urllib.request.urlopen(effective_url, timeout=timeout) as resp:  # noqa: S310
            length_hdr = resp.headers.get("Content-Length")
            total = int(length_hdr) if length_hdr and length_hdr.isdigit() else 0
            if total and total > max_bytes:
                raise BitbaseSizeExceeded(
                    f"Advertised size {total} bytes exceeds max_bytes={max_bytes}"
                )

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
                    if bytes_done > max_bytes:
                        raise BitbaseSizeExceeded(
                            f"Payload exceeded max_bytes={max_bytes} after "
                            f"{bytes_done} bytes"
                        )
                    if on_progress is not None:
                        on_progress(bytes_done, total)
    except BitbaseDownloadCancelled:
        tmp_path.unlink(missing_ok=True)
        raise
    except BitbaseSizeExceeded:
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
        logger.warning(
            "No expected SHA256 available — accepting file unverified "
            "(allow_unverified=True). SHA256 of received file: %s",
            actual,
        )

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
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=_DEFAULT_MAX_BYTES,
        help=f"Abort if payload exceeds this many bytes (default {_DEFAULT_MAX_BYTES})",
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Accept downloads without SHA-256 verification (not recommended)",
    )
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Allow http:// URLs (default: https:// only)",
    )
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
            max_bytes=args.max_bytes,
            allow_unverified=args.allow_unverified,
            allow_http=args.allow_http,
        )
    except BitbaseDownloadError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    print(f"\nDownloaded: {result.path}\n  size: {result.size_bytes / (1024 * 1024):.1f} MB\n  sha256: {result.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
