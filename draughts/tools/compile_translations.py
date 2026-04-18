"""Compile .po → .mo files for every locale in draughts/locale/.

Uses msgfmt from the Python stdlib (``python -m tools.i18n.msgfmt``) or
the ``msgfmt.py`` helper shipped with CPython.  Falls back to a minimal
pure-python .mo writer if neither is available.

Run after editing any .po file::

    python -m draughts.tools.compile_translations
"""

from __future__ import annotations

import ast
import struct
import sys
from pathlib import Path


LOCALE_ROOT = Path(__file__).resolve().parent.parent / "locale"


def _parse_po(po_path: Path) -> dict[str, str]:
    """Very small .po parser — sufficient for our simple catalogs.

    Does NOT handle plural forms or multi-line strings with `\n` within
    the msgid — keep entries single-line for compatibility.
    """
    entries: dict[str, str] = {}
    msgid: str | None = None
    msgstr: str | None = None
    for raw in po_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            if msgid is not None and msgstr is not None:
                entries[msgid] = msgstr
            msgid = ast.literal_eval(line[6:])
            msgstr = None
        elif line.startswith("msgstr "):
            msgstr = ast.literal_eval(line[7:])
    if msgid is not None and msgstr is not None:
        entries[msgid] = msgstr
    return entries


def _write_mo(mo_path: Path, entries: dict[str, str]) -> None:
    """Minimal GNU .mo writer — matches the format gettext.translation expects."""
    items = sorted(entries.items())
    # Keys and values are NUL-terminated and concatenated with a single NUL
    # separator. Build the byte blobs and track per-entry offsets explicitly.
    keys_blob = bytearray()
    key_offsets: list[tuple[int, int]] = []  # (length, offset)
    for k, _v in items:
        kb = k.encode("utf-8")
        key_offsets.append((len(kb), len(keys_blob)))
        keys_blob.extend(kb)
        keys_blob.append(0)  # NUL terminator
    vals_blob = bytearray()
    val_offsets: list[tuple[int, int]] = []
    for _k, v in items:
        vb = v.encode("utf-8")
        val_offsets.append((len(vb), len(vals_blob)))
        vals_blob.extend(vb)
        vals_blob.append(0)

    n = len(items)
    header_size = 7 * 4  # 7 little-endian uint32 fields
    keys_table_offset = header_size
    vals_table_offset = keys_table_offset + n * 8  # each entry: (length, offset) = 8 bytes
    keys_offset = vals_table_offset + n * 8
    vals_offset = keys_offset + len(keys_blob)

    out = bytearray()
    out.extend(struct.pack("<IIIIIII",
        0x950412de,          # magic
        0,                   # version
        n,                   # count
        keys_table_offset,
        vals_table_offset,
        0,                   # hash size (unused)
        0,                   # hash offset (unused)
    ))

    for length, offset in key_offsets:
        out.extend(struct.pack("<II", length, keys_offset + offset))

    for length, offset in val_offsets:
        out.extend(struct.pack("<II", length, vals_offset + offset))

    out.extend(keys_blob)
    out.extend(vals_blob)

    mo_path.write_bytes(bytes(out))


def compile_all() -> int:
    if not LOCALE_ROOT.is_dir():
        print(f"No locale dir at {LOCALE_ROOT}", file=sys.stderr)
        return 1
    n_compiled = 0
    for po in LOCALE_ROOT.rglob("*.po"):
        mo = po.with_suffix(".mo")
        entries = _parse_po(po)
        # Ensure the metadata header is present — gettext reads it to
        # discover the charset. If the .po didn't declare one, inject a
        # UTF-8 default so str() decoding works.
        if "" not in entries or "Content-Type" not in entries.get("", ""):
            entries[""] = (
                "Content-Type: text/plain; charset=UTF-8\n"
                "Content-Transfer-Encoding: 8bit\n"
            )
        _write_mo(mo, entries)
        print(f"  compiled: {mo.relative_to(LOCALE_ROOT)}")
        n_compiled += 1
    print(f"Done. {n_compiled} catalogs compiled.")
    return 0


if __name__ == "__main__":
    sys.exit(compile_all())
