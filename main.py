"""Entry point for the Draughts application."""

import sys

from PyQt6.QtWidgets import QApplication

from draughts.game.controller import GameController
from draughts.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Шашки")
    app.setApplicationVersion("0.1.0")

    controller = GameController()
    window = MainWindow(controller)
    window.show()

    # Start first game
    controller.new_game()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
