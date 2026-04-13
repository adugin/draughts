"""draughts.engine — engine text protocol layer.

Public API::

    from draughts.engine import EngineSession, run_engine_main

This package has NO PyQt6 imports — it is safe to use in headless / CI
environments without a Qt installation (enforced by D26).
"""

from __future__ import annotations

from .session import EngineSession


def run_engine_main() -> None:
    """Start an interactive engine session on stdin/stdout.

    Intended to be called from ``__main__.py`` (``python -m draughts.engine``).
    """
    import sys

    # Make stdout line-buffered so responses reach the caller immediately.
    session = EngineSession()
    session.run(sys.stdin, sys.stdout)


__all__ = ["EngineSession", "run_engine_main"]
