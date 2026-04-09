"""Entry point for the Draughts application."""

import sys

from PyQt6.QtWidgets import QApplication

from draughts.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Шашки")
    app.setApplicationVersion("0.1.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
