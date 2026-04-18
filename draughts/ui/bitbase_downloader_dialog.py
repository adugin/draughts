"""Qt dialog wrapping the bitbase downloader (D37).

Shows pre-flight info, runs the download in a background QThread,
reports progress via a QProgressBar, supports cancellation, and
notifies the caller of success/failure. On success, the app should
re-init DEFAULT_BITBASE so the new file takes effect without restart.
"""

from __future__ import annotations

import logging
import threading
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
    BitbaseInsecureURL,
    BitbaseIntegrityUnavailable,
    BitbaseSizeExceeded,
    DownloadResult,
    download_bitbase,
    get_destination_dir,
    resolve_url,
)

logger = logging.getLogger("draughts.bitbase_downloader_dialog")


class _DownloadWorker(QObject):
    """Runs the blocking download call; emits progress / finished signals.

    Cancellation uses a ``threading.Event`` (HIGH-09) — explicit
    cross-thread semantics, works under PyPy / nogil Python, and documents
    intent clearly. The downloader API still takes a ``list[bool]``
    sentinel, so we adapt via a tiny wrapper list that we flip when the
    event is set.
    """

    progress = pyqtSignal(int, int)  # bytes_done, bytes_total
    finished = pyqtSignal(object, object)  # (DownloadResult|None, error_msg|None)

    def __init__(self, url: str | None, dest_dir: Path | None) -> None:
        super().__init__()
        self._url = url
        self._dest_dir = dest_dir
        self._cancel_event = threading.Event()
        # Thin adapter: downloader polls this list each chunk.
        self._cancel_list: list[bool] = [False]

    def request_cancel(self) -> None:
        """Main-thread-safe: sets the Event; worker checks it next chunk."""
        self._cancel_event.set()
        self._cancel_list[0] = True

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def run(self) -> None:
        try:
            result = download_bitbase(
                url=self._url,
                dest_dir=self._dest_dir,
                on_progress=lambda d, t: self.progress.emit(d, t),
                cancel_flag=self._cancel_list,
            )
        except BitbaseDownloadCancelled:
            self.finished.emit(None, "Скачивание отменено")
            return
        except BitbaseChecksumMismatch as exc:
            self.finished.emit(
                None,
                f"Контрольная сумма не совпала — файл не прошёл проверку "
                f"целостности. Возможная подмена или ошибка передачи.\n\n{exc}",
            )
            return
        except BitbaseIntegrityUnavailable as exc:
            self.finished.emit(
                None,
                f"Файл SHA-256 (.sha256) не опубликован на релизе. "
                f"Загрузка отменена для безопасности.\n\n{exc}",
            )
            return
        except BitbaseSizeExceeded as exc:
            self.finished.emit(
                None,
                f"Файл слишком большой (больше установленного лимита). "
                f"Загрузка отменена.\n\n{exc}",
            )
            return
        except BitbaseInsecureURL as exc:
            self.finished.emit(
                None,
                f"Источник использует небезопасный протокол (не HTTPS). "
                f"Загрузка отменена.\n\n{exc}",
            )
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
        # Set when the user closes the window via its [X] while a
        # download is in flight; read in _on_finished so the dialog
        # self-closes once the worker wraps up, regardless of outcome.
        self._close_pending: bool = False

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

        # MED-06: make URL a clickable hyperlink so the user can inspect
        # the release page in a browser.
        self._url_label = QLabel(
            f'<b>Источник:</b> <a href="{self._url}">{self._url}</a>'
        )
        self._url_label.setTextFormat(Qt.TextFormat.RichText)
        self._url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._url_label.setOpenExternalLinks(True)
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
            # Signal the worker via threading.Event; it will raise
            # BitbaseDownloadCancelled, emit finished(), and the signal
            # chain from _on_start handles teardown automatically.
            self._worker.request_cancel()
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
        # HIGH-08 fix: quit → wait → deleteLater in this order.
        # Clearing refs BEFORE wait() so a re-entrant start() can build
        # a new thread even while we're still joining the old one.
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

        # User closed the window via [X] while the download was in
        # flight — honour that intent unconditionally, regardless of
        # whether the worker finished cleanly, errored out, or was
        # cancelled. Skipping the outcome dialogs avoids re-focusing a
        # window the user already dismissed.
        if self._close_pending:
            self.reject()
            return

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

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Handle [X]/Alt-F4 while a download may still be running.

        Without this hook, closing the window via the title-bar button
        left the worker thread alive and the _DownloadWorker C++ object
        pending deletion — the next start() on a subsequent open would
        see ``_thread is not None`` and silently no-op. Now we request
        cancellation, suppress the close, and let ``_on_finished`` call
        ``reject()`` once the worker exits cleanly.
        """
        if self._thread is not None and self._thread.isRunning():
            self._close_pending = True
            if self._worker is not None and not self._worker.is_cancelled():
                self._worker.request_cancel()
                self._status.setText("Отмена...")
                self._btn_cancel.setEnabled(False)
            event.ignore()
            return
        event.accept()
