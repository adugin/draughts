"""Entry point for the Draughts application."""

import sys

from PyQt6.QtWidgets import QApplication

from draughts.game.controller import GameController
from draughts.ui.main_window import MainWindow
from draughts.ui.splash import SplashScreen


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Шашки")
    app.setApplicationVersion("0.1.0")

    controller = GameController()
    window = MainWindow(controller)

    # Show splash screen first
    splash = SplashScreen()

    def on_splash_finished():
        splash.close()
        window.show()
        controller.new_game()

    splash.finished.connect(on_splash_finished)
    splash.show_animated()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
