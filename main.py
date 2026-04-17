"""Entry point for the Draughts application.

Usage:
    python main.py                     # New game with default settings
    python main.py game.json           # Load saved game
    python main.py --resume            # Continue from autosave
    python main.py --difficulty 3      # Start at Professional level
    python main.py --black             # Play as black
    python main.py --version           # Show version and exit
"""

import argparse
import sys
from pathlib import Path

import draughts
from draughts.app.controller import GameController
from draughts.config import AUTOSAVE_FILENAME, get_data_dir
from draughts.ui.main_window import MainWindow
from PyQt6.QtWidgets import QApplication


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draughts",
        description="Русские шашки — игра с компьютерным противником",
    )
    parser.add_argument(
        "savefile",
        nargs="?",
        default=None,
        help="JSON-файл сохранённой партии для загрузки при старте",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="продолжить прерванную партию (загрузить автосохранение)",
    )
    parser.add_argument(
        "--difficulty",
        type=int,
        choices=[1, 2, 3, 4, 5, 6],
        default=None,
        help=(
            "уровень сложности: "
            "1=Новичок (~800), 2=Любитель (~1100), 3=Клубный (~1400), "
            "4=Сильный клубный (~1700), 5=Кандидат (~2000), 6=Мастер (~2200+)"
        ),
    )
    parser.add_argument(
        "--black",
        action="store_true",
        help="играть чёрными (компьютер играет белыми)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {draughts.__version__}",
    )
    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    # Resolve save file: explicit file > --resume > none
    load_path: str | None = None
    if args.savefile:
        p = Path(args.savefile)
        if not p.exists():
            parser.error(f"файл не найден: {args.savefile}")
        load_path = str(p)
    elif args.resume:
        autosave_path = get_data_dir() / AUTOSAVE_FILENAME
        if autosave_path.exists():
            load_path = str(autosave_path)

    app = QApplication(sys.argv)
    from draughts.config import APP_NAME
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(draughts.__version__)

    controller = GameController()

    # Load saved user preferences (or defaults if no settings file)
    from draughts.config import load_settings
    controller.settings = load_settings()

    # CLI flags override saved settings
    if args.difficulty is not None:
        controller.settings.difficulty = args.difficulty
    if args.black:
        controller.settings.invert_color = True

    window = MainWindow(controller)
    window.show()

    # Load saved game or start new
    if load_path:
        try:
            controller.load_saved_game(load_path)
            # Apply loaded invert_color flag to the widget — MainWindow
            # sampled it once in _connect_controller with the defaults, so
            # it would still be False here without an explicit sync.
            window.board_widget.inverted = controller.settings.invert_color
        except Exception as e:
            print(f"Ошибка загрузки {load_path}: {e}", file=sys.stderr)
            controller.new_game()
    else:
        controller.new_game()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
