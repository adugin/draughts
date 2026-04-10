"""Entry point for the Draughts application."""

import sys

from draughts.game.controller import GameController
from draughts.ui.main_window import MainWindow
from PyQt6.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Шашки")
    app.setApplicationVersion("2.0.0")

    controller = GameController()
    window = MainWindow(controller)
    window.show()
    controller.new_game()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
