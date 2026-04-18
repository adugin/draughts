"""Qt dialog wrapping the bitbase downloader (D37).

Shows pre-flight info, runs the download in a background QThread,
reports progress via a QProgressBar, supports cancellation, and
notifies the caller of success/failure. On success, the app should
re-init DEFAULT_BITBASE so the new file takes effect without restart.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from draughts.tools.bitbase_downloader import (
    BitbaseChecksumMismatch,
    BitbaseDownloadCancelled,
    BitbaseDownloadError,
    DownloadResult,
    download_bitbase,
    get_destination_dir,
    resolve_url,
)

logger = logging.getLogger("draughts.bitbase_downloader_dialog")


class _DownloadWorker(QObject):
    """Runs the blocking download call; emits progress / finished signals."""

    progress = pyqtSignal(int, int)  # bytes_done, bytes_total
    finished = pyqtSignal(object, object)  # (DownloadResult|None, error_msg|None)

    def __init__(self, url: str | None, dest_dir: Path | None) -> None:
        super().__init__()
        self._url = url
        self._dest_dir = dest_dir
        self.cancel_flag: list[bool] = [False]

    def run(self) -> None:
        try:
            result = download_bitbase(
                url=self._url,
                dest_dir=self._dest_dir,
                on_progress=lambda d, t: self.progress.emit(d, t),
                cancel_flag=self.cancel_flag,
            )
        except BitbaseDownloadCancelled:
            self.finished.emit(None, "Скачивание отменено")
            return
        except BitbaseChecksumMismatch as exc:
            self.finished.emit(None, f"Проверка целостности не пройдена:\n{exc}")
            return
        except BitbaseDownloadError as exc:
            self.finished.emit(None, f"Ошибка загрузки:\n{exc}")
            return
        except Exception as exc:  # defensive — unexpected
            logger.exception("Unexpected error in bitbase downloader worker")
            self.finished.emit(None, f"Неожиданная ошибка:\n{exc}")
            return
        self.finished.emit(result, None)


class BitbaseDownloaderDialog(QDialog):
    """Modal-ish dialog that downloads the 4-piece bitbase with progress.

    Despite being a modal QDialog, the game QMainWindow remains alive
    underneath — only this dialog blocks. The D36 "non-modal" guidance
    applies to long-running *generation* jobs; a ~1-minute download is
    acceptable as a modal dialog and keeps the flow simple.
    """

    #: Emitted when a download completes successfully, with the destination path.
    downloaded = pyqtSignal(object)  # Path

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Загрузка эндшпильной базы (4 фигуры)")
        self.setModal(True)
        self.resize(500, 240)

        self._url = resolve_url(None)
        self._dest_dir = get_destination_dir()

        self._worker: _DownloadWorker | None = None
        self._thread: QThread | None = None
        self._result_path: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        intro = QLabel(
            "Будет скачан файл эндшпильной базы на 4 фигуры (~126 МБ, сжатый)\n"
            "с GitHub Releases. После проверки контрольной суммы файл\n"
            "сохраняется в папку пользователя и подхватывается движком\n"
            "автоматически."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._url_label = QLabel(f"<b>Источник:</b> <code>{self._url}</code>")
        self._url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._url_label)

        self._dest_label = QLabel(f"<b>Назначение:</b> <code>{self._dest_dir}</code>")
        self._dest_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._dest_label)

        self._status = QLabel("Готов к загрузке.")
        root.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        root.addWidget(self._progress)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_start = QPushButton("Скачать")
        self._btn_start.setDefault(True)
        self._btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self._btn_start)

        self._btn_cancel = QPushButton("Отмена")
        self._btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._btn_cancel)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        if self._thread is not None:
            return  # already running
        self._btn_start.setEnabled(False)
        self._status.setText("Скачивание...")
        self._progress.setValue(0)

        self._thread = QThread(self)
        self._worker = _DownloadWorker(self._url, self._dest_dir)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _on_cancel(self) -> None:
        if self._worker is not None and self._thread is not None:
            # Signal the worker; it will finish and emit finished() with
            # a cancellation message, and we tear the thread down there.
            self._worker.cancel_flag[0] = True
            self._btn_cancel.setEnabled(False)
            self._status.setText("Отмена...")
        else:
            # Nothing running — just close.
            self.reject()

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(done)
            self._status.setText(
                f"Скачано: {done / (1024 * 1024):.1f} / {total / (1024 * 1024):.1f} МБ"
            )
        else:
            # Unknown total — show indeterminate progress in bytes.
            self._progress.setMaximum(0)
            self._status.setText(f"Скачано: {done / (1024 * 1024):.1f} МБ")

    def _on_finished(self, result: DownloadResult | None, error_msg: str | None) -> None:
        # Tear down worker/thread safely.
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None

        if error_msg is not None:
            self._status.setText("Не выполнено")
            QMessageBox.warning(self, "Загрузка не выполнена", error_msg)
            self.reject()
            return

        assert result is not None
        self._result_path = result.path
        self._status.setText(
            f"Готово. {result.size_bytes / (1024 * 1024):.1f} МБ записано в {result.path.name}"
        )
        self._progress.setMaximum(100)
        self._progress.setValue(100)
        self.downloaded.emit(result.path)

        # Swap buttons: cancel → close.
        self._btn_start.setVisible(False)
        self._btn_cancel.setText("Закрыть")
        self._btn_cancel.setEnabled(True)
        try:
            self._btn_cancel.clicked.disconnect()
        except TypeError:
            pass
        self._btn_cancel.clicked.connect(self.accept)

    @property
    def result_path(self) -> Path | None:
        return self._result_path
