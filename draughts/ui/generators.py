"""Generator framework + dialogs for in-app data generation (D36).

D36 scope:
    * ВКЛЮЧЕНО в меню «Инструменты»: импорт книги из PDN, добыча задач.
    * НЕ ВКЛЮЧЕНО: retrograde bitbase generation, Texel tuning.

Shared infrastructure:
    GeneratorProgressDialog — non-modal dock-like window showing a
    progress bar, log area, and cancel button. Re-usable across all
    D36 generators.

    _GeneratorWorker — QThread-friendly wrapper that runs a callable
    taking (on_progress, should_cancel) and emits success/failure.

Data lives in %APPDATA%/DRAUGHTS/generated/ (see ``_output_dir()``).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

logger = logging.getLogger("draughts.generators")


# Output paths were previously centralised through ``_output_dir()`` but
# the audit (BLK-01, BLK-02, PO-4) required splitting per content type:
# books live under books_dir(), puzzles under puzzles_dir(). The
# dialogs below import directly from draughts.user_data so the loaders
# and the generators can never disagree about the target path again.


# ---------------------------------------------------------------------------
# Worker framework
# ---------------------------------------------------------------------------


#: Signature for a generator function: (on_progress, should_cancel) → result dict.
#: on_progress takes (current, total, message) — all optional.
#: should_cancel is a zero-arg callable returning True when the user pressed Cancel.
GeneratorFn = Callable[
    [Callable[[int, int, str], None], Callable[[], bool]],
    dict[str, Any],
]


class _GeneratorWorker(QObject):
    """Runs a GeneratorFn in a background QThread.

    The worker is plain-Python-cooperative with cancellation: the
    generator function checks ``should_cancel()`` at safe points and
    returns gracefully. We do NOT kill the thread forcibly.
    """

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(object, object)  # (result|None, error_msg|None)

    def __init__(self, fn: GeneratorFn) -> None:
        super().__init__()
        self._fn = fn
        # HIGH-09: threading.Event — explicit cross-thread semantics,
        # works under PyPy / nogil Python.
        self._cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            result = self._fn(self._emit_progress, self._should_cancel)
        except _GeneratorCancelled:
            self.finished.emit(None, "cancelled")
            return
        except Exception as exc:  # defensive
            logger.exception("Generator crashed")
            self.finished.emit(None, f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(result, None)

    def _emit_progress(self, current: int, total: int, message: str = "") -> None:
        self.progress.emit(current, total, message)

    def _should_cancel(self) -> bool:
        return self._cancel_event.is_set()


class _GeneratorCancelled(RuntimeError):
    """Raised by a generator when it detects a cancel request."""


# ---------------------------------------------------------------------------
# Progress dialog (non-modal)
# ---------------------------------------------------------------------------


class GeneratorProgressDialog(QDialog):
    """Non-modal progress window for D36 generators.

    ``fn`` is the generator to run. ``title`` appears in the window
    title. ``on_done`` (optional) receives the result dict on success.
    Emits ``completed(result_dict)`` on success for Qt-signal-style
    wiring.
    """

    completed = pyqtSignal(object)  # result dict

    def __init__(self, fn: GeneratorFn, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        # Non-modal: user can keep playing while generation runs.
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Tool)
        self.resize(520, 340)

        self._fn = fn
        self._thread: QThread | None = None
        self._worker: _GeneratorWorker | None = None
        self._result: dict[str, Any] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(8)

        self._status = QLabel("Готов к запуску.")
        root.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        root.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(150)
        root.addWidget(self._log, stretch=1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self._btn_close = QPushButton("Закрыть")
        self._btn_close.clicked.connect(self._on_close_clicked)
        btns.addWidget(self._btn_close)
        self._btn_cancel = QPushButton("Отмена")
        self._btn_cancel.clicked.connect(self._on_cancel_clicked)
        btns.addWidget(self._btn_cancel)
        root.addLayout(btns)

        self._btn_cancel.setEnabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Kick off the background worker."""
        if self._thread is not None:
            return
        self._status.setText("Работа...")
        self._btn_cancel.setEnabled(True)
        self._btn_close.setEnabled(False)

        self._thread = QThread(self)
        self._worker = _GeneratorWorker(self._fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def append_log(self, line: str) -> None:
        self._log.append(line)

    @property
    def result(self) -> dict[str, Any] | None:
        return self._result

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_progress(self, current: int, total: int, message: str) -> None:
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(min(current, total))
        else:
            self._progress.setMaximum(0)
        if message:
            self.append_log(message)

    def _on_finished(self, result: dict[str, Any] | None, error_msg: str | None) -> None:
        # Tear down thread+worker.  Important order (HIGH-08):
        #   1. thread.quit() asks the worker thread's event loop to exit.
        #   2. thread.wait() blocks until it actually exits (fast — the
        #      worker's last signal was already delivered before we got
        #      here).
        #   3. At that point the worker C++ object is still alive but no
        #      longer has an event loop to post to — so we deleteLater
        #      via the PARENT (main) thread's event loop, not the dead
        #      worker thread.
        #   4. Same for thread itself.
        worker = self._worker
        thread = self._thread
        self._worker = None
        self._thread = None
        if thread is not None:
            thread.quit()
            thread.wait()
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()

        self._btn_cancel.setEnabled(False)
        self._btn_close.setEnabled(True)

        if error_msg == "cancelled":
            self._status.setText("Отменено пользователем.")
            self.append_log("— отмена —")
            return
        if error_msg is not None:
            self._status.setText("Ошибка.")
            self.append_log(f"ОШИБКА: {error_msg}")
            return

        self._result = result
        self._status.setText("Готово.")
        if result is not None:
            self.append_log(f"Результат: {result}")
        self.completed.emit(result)

    def _on_cancel_clicked(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
            self._status.setText("Отмена...")
            self._btn_cancel.setEnabled(False)

    def _on_close_clicked(self) -> None:
        if self._worker is not None:
            # Still running — treat close as cancel.
            self._on_cancel_clicked()
            return
        self.accept()


# ---------------------------------------------------------------------------
# "Import book from PDN..." dialog
# ---------------------------------------------------------------------------


class ImportBookFromPdnDialog(QDialog):
    """Parameter dialog + progress window for book import."""

    imported = pyqtSignal(object)  # Path of the produced book

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Импорт книги из PDN")
        self.setModal(True)
        self.resize(460, 220)

        self._pdn_paths: list[Path] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(8)

        root.addWidget(
            QLabel(
                "Выберите один или несколько PDN-файлов с партиями.\n"
                "Первые N ходов каждой партии будут добавлены в опорную\n"
                "книгу; веса накапливаются при повторных позициях."
            )
        )

        files_row = QHBoxLayout()
        self._files_label = QLabel("<i>файлы не выбраны</i>")
        self._files_label.setWordWrap(True)
        files_row.addWidget(self._files_label, stretch=1)
        btn_browse = QPushButton("Выбрать...")
        btn_browse.clicked.connect(self._on_browse)
        files_row.addWidget(btn_browse)
        root.addLayout(files_row)

        params_row = QHBoxLayout()
        params_row.addWidget(QLabel("Полуходов на партию:"))
        self._plies = QSpinBox()
        self._plies.setRange(4, 40)
        self._plies.setValue(16)
        params_row.addWidget(self._plies)
        params_row.addStretch(1)
        root.addLayout(params_row)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self._btn_ok = QPushButton("Импортировать")
        self._btn_ok.setDefault(True)
        self._btn_ok.setEnabled(False)
        self._btn_ok.clicked.connect(self._on_ok)
        btns.addWidget(self._btn_ok)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        root.addLayout(btns)

    def _on_browse(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "PDN файлы", "", "PDN (*.pdn);;All (*)")
        if not files:
            return
        self._pdn_paths = [Path(f) for f in files]
        if len(self._pdn_paths) == 1:
            self._files_label.setText(str(self._pdn_paths[0]))
        else:
            self._files_label.setText(f"{len(self._pdn_paths)} файлов выбрано")
        self._btn_ok.setEnabled(True)

    def _on_ok(self) -> None:
        from draughts.user_data import user_book_path

        out_path = user_book_path()
        plies = self._plies.value()
        pdn_paths = list(self._pdn_paths)

        def fn(on_progress, should_cancel) -> dict[str, Any]:
            from draughts.game.ai.book import OpeningBook
            from draughts.game.pdn import load_pdn_file
            from draughts.tools.import_book_from_pdn import import_games

            book = OpeningBook.load(out_path) if out_path.exists() else OpeningBook()
            total_games = 0
            for i, pdn_path in enumerate(pdn_paths):
                if should_cancel():
                    raise _GeneratorCancelled()
                on_progress(i, len(pdn_paths), f"Читаю {pdn_path.name}...")
                try:
                    games = load_pdn_file(pdn_path)
                except Exception as exc:
                    on_progress(i, len(pdn_paths), f"  ошибка: {exc}")
                    continue
                before_positions = len(book)
                import_games(games, plies=plies, book=book)
                added = len(book) - before_positions
                total_games += len(games)
                on_progress(i + 1, len(pdn_paths), f"  {len(games)} партий → +{added} позиций")
                if should_cancel():
                    raise _GeneratorCancelled()

            on_progress(len(pdn_paths), len(pdn_paths), f"Сохраняю в {out_path}...")
            book.save(out_path)
            return {"path": out_path, "games": total_games, "positions": len(book)}

        # MED-01 fix: attach progress dialog to the MainWindow (not to
        # self, which is about to be accepted and GC'd). This keeps
        # the non-modal dialog alive for the whole run.
        parent = self.parent() or self
        self.accept()
        progress = GeneratorProgressDialog(fn, "Импорт книги из PDN", parent)
        progress.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        progress.completed.connect(self._on_import_completed)
        progress.show()
        progress.start()
        if hasattr(parent, "_active_generators"):
            parent._active_generators.append(progress)

    def _on_import_completed(self, result) -> None:
        if result is None:
            return
        # Re-init DEFAULT_BOOK so the new file takes effect without restart.
        try:
            from draughts.game.ai import load_default_book

            load_default_book()
        except Exception:
            logger.exception("Failed to reload default book after import")
        self.imported.emit(result.get("path"))


# ---------------------------------------------------------------------------
# "Mine puzzles..." dialog
# ---------------------------------------------------------------------------


class MinePuzzlesDialog(QDialog):
    """Parameter dialog + progress window for puzzle mining."""

    mined = pyqtSignal(object)  # Path of the produced puzzle file

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Добыча тактических задач")
        self.setModal(True)
        self.resize(460, 220)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(8)

        root.addWidget(
            QLabel(
                "Программа сыграет N асимметричных партий (уровень 1 против\n"
                "уровня 6) с разными начальными ходами и выделит ошибки как\n"
                "тренировочные задачи.\n\n"
                "Ориентировочно: 1 партия ≈ 10 секунд."
            )
        )

        row = QHBoxLayout()
        row.addWidget(QLabel("Количество партий:"))
        self._games = QSpinBox()
        self._games.setRange(5, 500)
        self._games.setValue(30)
        self._games.setSingleStep(5)
        row.addWidget(self._games)
        row.addStretch(1)
        root.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Случайное зерно (0 = случайно):"))
        self._seed = QSpinBox()
        self._seed.setRange(0, 2 ** 31 - 1)
        self._seed.setValue(0)
        row2.addWidget(self._seed)
        row2.addStretch(1)
        root.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Глубина оценки позиций:"))
        self._depth = QSpinBox()
        # Depth 4 is the minimum for reliable blunder detection — matches
        # the batch miner (see draughts/tools/mine_puzzles_batch.py).
        # Depth 3 was rejected by the M6 audit (MED-02) as under-powered
        # for the engine that later plays the puzzle at depth 5.
        self._depth.setRange(4, 8)
        self._depth.setValue(4)
        row3.addWidget(self._depth)
        row3.addWidget(
            QLabel(
                "<i>(глубже — точнее, но дольше; рекомендуется 4)</i>"
            )
        )
        row3.addStretch(1)
        root.addLayout(row3)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self._btn_ok = QPushButton("Запустить")
        self._btn_ok.setDefault(True)
        self._btn_ok.clicked.connect(self._on_ok)
        btns.addWidget(self._btn_ok)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        root.addLayout(btns)

    def _on_ok(self) -> None:
        n_games = self._games.value()
        seed_value = self._seed.value()
        analysis_depth = self._depth.value()

        def fn(on_progress, should_cancel) -> dict[str, Any]:
            import random as _random
            import time

            from draughts.game.puzzle_miner import (
                append_mined_puzzles,
                load_mined_puzzles,
                mine_puzzles_from_game,
            )
            from draughts.tools.mine_puzzles_batch import play_selfplay_game
            from draughts.ui.game_analyzer import analyze_game_positions
            from draughts.user_data import mined_puzzles_path

            if seed_value:
                _random.seed(seed_value)
            else:
                _random.seed(time.time_ns() & 0xFFFFFFFF)

            existing_before = len(load_mined_puzzles())
            collected: list[dict] = []

            for i in range(n_games):
                if should_cancel():
                    raise _GeneratorCancelled()
                opening_plies = (i % 5) + 1
                positions = play_selfplay_game(opening_plies=opening_plies)
                if len(positions) < 4:
                    on_progress(i + 1, n_games, f"партия {i + 1}: слишком короткая")
                    continue
                result = analyze_game_positions(positions, depth=analysis_depth)
                new_puzzles = mine_puzzles_from_game(
                    positions, result.annotations, min_delta_cp=2.0
                )
                collected.extend(new_puzzles)
                on_progress(
                    i + 1, n_games,
                    f"партия {i + 1}/{n_games}: +{len(new_puzzles)} задач "
                    f"(суммарно собрано {len(collected)})",
                )

            if should_cancel():
                raise _GeneratorCancelled()

            # append_mined_puzzles handles dedup by position and atomic-
            # ish write to the single canonical puzzles dir.
            on_progress(n_games, n_games, "Сохраняю...")
            added = append_mined_puzzles(collected)
            total_now = existing_before + added
            return {
                "path": mined_puzzles_path(),
                "added": added,
                "total": total_now,
            }

        parent = self.parent() or self
        self.accept()
        progress = GeneratorProgressDialog(fn, "Добыча задач", parent)
        progress.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        progress.completed.connect(self._on_mine_completed)
        progress.show()
        progress.start()
        if hasattr(parent, "_active_generators"):
            parent._active_generators.append(progress)

    def _on_mine_completed(self, result) -> None:
        if result is None:
            return
        path = result.get("path")
        total = result.get("total", 0)
        added = result.get("added", 0)
        self.mined.emit(path)
        QMessageBox.information(
            self.parent(),
            "Задачи добыты",
            f"Добавлено новых: {added}\n"
            f"Всего в базе пользователя: {total}\n"
            f"Файл: {path}\n\n"
            "Новые задачи будут предложены в тренажёре вместе со встроенными.",
        )
