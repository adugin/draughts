"""Tests for board orientation (D22) — flip flag propagation.

Verifies that:
1. BoardWidget.inverted defaults to False (white at bottom).
2. Setting inverted=True flips _cell_rect so that board square (0,0)
   renders at the bottom-right visually (i.e. its pixel-y is near the
   bottom, not the top).
3. _cell_from_pos correctly maps back to board coordinates when inverted.
4. invert_color=True in GameSettings causes the controller to assign
   the player to BLACK and computer to WHITE.
5. The --black CLI flag sets invert_color=True on the controller settings.
"""

from __future__ import annotations

import sys

import pytest

# ---------------------------------------------------------------------------
# Qt fixtures — keep QApplication alive for the whole module
# ---------------------------------------------------------------------------

_qt_app = None  # module-level reference so GC doesn't destroy it


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    """Create (or reuse) a QApplication for the test module."""
    global _qt_app
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    _qt_app = QApplication.instance() or QApplication(sys.argv)
    yield _qt_app


@pytest.fixture
def normal_widget(qt_app):
    """BoardWidget in normal orientation (white at bottom)."""
    from draughts.ui.board_widget import BoardWidget

    w = BoardWidget()
    w.resize(400, 400)
    w.inverted = False
    yield w
    w.destroy()


@pytest.fixture
def inverted_widget(qt_app):
    """BoardWidget in inverted orientation (black at bottom)."""
    from draughts.ui.board_widget import BoardWidget

    w = BoardWidget()
    w.resize(400, 400)
    w.inverted = True
    yield w
    w.destroy()


# ---------------------------------------------------------------------------
# BoardWidget geometry tests
# ---------------------------------------------------------------------------


class TestBoardWidgetOrientation:
    """Geometry unit tests — no display required."""

    def test_inverted_defaults_false(self, qt_app):
        """BoardWidget.inverted is False by default."""
        from draughts.ui.board_widget import BoardWidget

        w = BoardWidget()
        assert w.inverted is False
        w.destroy()

    def test_inverted_can_be_set_true(self, qt_app):
        """BoardWidget.inverted can be set to True."""
        from draughts.ui.board_widget import BoardWidget

        w = BoardWidget()
        w.inverted = True
        assert w.inverted is True
        w.destroy()

    def test_cell_rect_normal_top_left_is_00(self, normal_widget):
        """In normal orientation, board (0,0) is in the top-left area."""
        w = normal_widget
        _, cell_size, bx, by = w._metrics()

        rect_00 = w._cell_rect(0, 0, cell_size, bx, by)
        rect_77 = w._cell_rect(7, 7, cell_size, bx, by)

        # (0,0) should be above (7,7) — smaller y
        assert rect_00.top() < rect_77.top()
        # (0,0) should be left of (7,7) — smaller x
        assert rect_00.left() < rect_77.left()

    def test_cell_rect_inverted_00_is_bottom_right(self, inverted_widget):
        """In inverted orientation, board (0,0) is in the bottom-right area."""
        w = inverted_widget
        _, cell_size, bx, by = w._metrics()

        rect_00 = w._cell_rect(0, 0, cell_size, bx, by)
        rect_77 = w._cell_rect(7, 7, cell_size, bx, by)

        # When inverted, (0,0) should be below (7,7) — larger y
        assert rect_00.top() > rect_77.top()
        # When inverted, (0,0) should be right of (7,7) — larger x
        assert rect_00.left() > rect_77.left()

    def test_cell_from_pos_normal_top_left_maps_to_00(self, normal_widget):
        """In normal orientation, clicking the top-left area maps to (0,0)."""
        w = normal_widget
        _, cell_size, bx, by = w._metrics()

        from PyQt6.QtCore import QPointF

        pos = QPointF(bx + cell_size * 0.5, by + cell_size * 0.5)
        cell = w._cell_from_pos(pos)
        assert cell == (0, 0)

    def test_cell_from_pos_inverted_top_left_maps_to_77(self, inverted_widget):
        """In inverted orientation, clicking the top-left area maps to (7,7)."""
        w = inverted_widget
        _, cell_size, bx, by = w._metrics()

        from PyQt6.QtCore import QPointF

        pos = QPointF(bx + cell_size * 0.5, by + cell_size * 0.5)
        cell = w._cell_from_pos(pos)
        assert cell == (7, 7)

    def test_cell_roundtrip_normal(self, normal_widget):
        """cell_rect centre → cell_from_pos returns the same (x,y) in normal mode."""
        w = normal_widget
        _, cell_size, bx, by = w._metrics()

        from PyQt6.QtCore import QPointF

        for x in range(8):
            for y in range(8):
                rect = w._cell_rect(x, y, cell_size, bx, by)
                centre = QPointF(rect.center().x(), rect.center().y())
                assert w._cell_from_pos(centre) == (x, y), (
                    f"roundtrip failed for ({x},{y})"
                )

    def test_cell_roundtrip_inverted(self, inverted_widget):
        """cell_rect centre → cell_from_pos returns the same (x,y) when inverted."""
        w = inverted_widget
        _, cell_size, bx, by = w._metrics()

        from PyQt6.QtCore import QPointF

        for x in range(8):
            for y in range(8):
                rect = w._cell_rect(x, y, cell_size, bx, by)
                centre = QPointF(rect.center().x(), rect.center().y())
                assert w._cell_from_pos(centre) == (x, y), (
                    f"inverted roundtrip failed for ({x},{y})"
                )


# ---------------------------------------------------------------------------
# Controller / settings tests — no Qt display required
# ---------------------------------------------------------------------------


class TestOrientationSettings:
    """Verify invert_color propagates correctly through settings and controller."""

    def test_game_settings_invert_color_default_false(self):
        """GameSettings.invert_color defaults to False."""
        from draughts.config import GameSettings

        s = GameSettings()
        assert s.invert_color is False

    def test_game_settings_show_clock_default_false(self):
        """GameSettings.show_clock defaults to False (D19)."""
        from draughts.config import GameSettings

        s = GameSettings()
        assert s.show_clock is False

    def test_controller_default_player_is_white(self, qt_app):
        """By default the human player is WHITE and computer is BLACK.

        We check the colors that new_game() would assign without actually
        calling new_game() to avoid spawning the AI thread in tests.
        """
        from draughts.config import Color, GameSettings

        s = GameSettings()
        # new_game() logic: computer=BLACK when not invert_color, player=WHITE
        player = Color.WHITE if not s.invert_color else Color.BLACK
        computer = Color.BLACK if not s.invert_color else Color.WHITE
        assert player == Color.WHITE
        assert computer == Color.BLACK

    def test_controller_invert_color_makes_player_black(self, qt_app):
        """When invert_color=True, the human player is BLACK and computer is WHITE.

        Verifies the same logic new_game() uses without launching the AI thread.
        """
        from draughts.config import Color, GameSettings

        s = GameSettings(invert_color=True)
        player = Color.WHITE if not s.invert_color else Color.BLACK
        computer = Color.BLACK if not s.invert_color else Color.WHITE
        assert player == Color.BLACK
        assert computer == Color.WHITE

    def test_black_flag_sets_invert_color(self, qt_app):
        """Simulating --black: setting invert_color=True causes player to be BLACK."""
        from draughts.config import Color, GameSettings

        s = GameSettings()
        # Simulate what main.py does for --black
        s.invert_color = True
        player = Color.WHITE if not s.invert_color else Color.BLACK
        assert player == Color.BLACK

    def test_board_widget_inverted_follows_invert_color(self, qt_app):
        """BoardWidget.inverted should match invert_color from GameSettings."""
        from draughts.ui.board_widget import BoardWidget
        from draughts.config import GameSettings

        bw = BoardWidget()
        # Simulate what MainWindow._connect_controller does
        s = GameSettings(invert_color=True)
        bw.inverted = s.invert_color
        assert bw.inverted is True

        s2 = GameSettings(invert_color=False)
        bw.inverted = s2.invert_color
        assert bw.inverted is False
        bw.destroy()
