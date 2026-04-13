# Backward-compat shim — controller lives in draughts.app now
from draughts.app.controller import AIWorker, GameController  # noqa: F401
