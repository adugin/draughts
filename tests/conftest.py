"""Common fixtures for draughts tests."""

import pytest
from draughts.game.board import Board


@pytest.fixture
def board():
    """Fresh board with standard starting position."""
    return Board()


@pytest.fixture
def empty_board():
    """Empty board with no pieces."""
    return Board(empty=True)
