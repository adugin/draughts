"""Entry point for the Draughts application."""

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from draughts.game.controller import GameController
from draughts.ui.main_window import MainWindow
from draughts.ui.splash import SplashScreen


def _save_screenshot(widget, filename: str):
    """Grab a widget and save it as PNG."""
    pixmap = widget.grab()
    pixmap.save(filename, "PNG")
    print(f"Screenshot saved: {filename}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Шашки")
    app.setApplicationVersion("1.0.0")

    screenshot_mode = None
    if "--screenshot" in sys.argv:
        idx = sys.argv.index("--screenshot")
        screenshot_mode = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "all"

    no_splash = "--no-splash" in sys.argv

    controller = GameController()
    window = MainWindow(controller)

    if no_splash and screenshot_mode is None:
        window.show()
        controller.new_game()

    elif screenshot_mode in ("splash", "all"):
        splash = SplashScreen()

        def on_splash_phase(phase_name, widget):
            _save_screenshot(widget, f"screenshot_splash_{phase_name}.png")

        splash._screenshot_callback = on_splash_phase

        def on_splash_finished():
            splash.close()
            window.show()
            controller.new_game()
            if screenshot_mode in ("window", "all"):
                QTimer.singleShot(500, lambda: (
                    _save_screenshot(window, "screenshot_window.png"),
                    app.quit(),
                ))
            else:
                app.quit()

        splash.finished.connect(on_splash_finished)
        splash.show_animated()

    elif screenshot_mode == "window":
        window.show()
        controller.new_game()
        QTimer.singleShot(500, lambda: (
            _save_screenshot(window, "screenshot_window.png"),
            app.quit(),
        ))

    else:
        # Normal mode
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
