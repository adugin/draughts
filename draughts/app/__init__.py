"""App layer — PyQt6 application wiring (controller, resources).

This package bridges the pure game logic (draughts.game) and the UI
layer (draughts.ui).  All PyQt6 dependencies are confined here.
"""

from draughts.app.controller import AIWorker, GameController  # noqa: F401
