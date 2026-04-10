"""Dialog windows for the draughts application.

All dialogs use standard PyQt6 widgets for a clean, native Windows look.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from draughts.config import GameSettings

# ---------------------------------------------------------------------------
# 1. OptionsDialog
# ---------------------------------------------------------------------------


class OptionsDialog(QDialog):
    """Settings dialog — difficulty, speed, hints, sound, delay, etc."""

    def __init__(self, settings: GameSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Опции")
        self.setModal(True)

        self._settings = settings

        layout = QFormLayout(self)

        # Difficulty
        self._difficulty = QComboBox()
        self._difficulty.addItems(["Любитель", "Нормал", "Профессионал"])
        self._difficulty.setCurrentIndex(settings.difficulty - 1)
        layout.addRow("Сложность:", self._difficulty)

        # Remind
        self._remind = QCheckBox("Подсказка взятия")
        self._remind.setChecked(settings.remind)
        layout.addRow(self._remind)

        # Sound
        self._sound = QCheckBox("Звук")
        self._sound.setChecked(settings.sound_effect)
        layout.addRow(self._sound)

        # Pause (delay multiplier)
        self._pause = QDoubleSpinBox()
        self._pause.setRange(0.0, 5.0)
        self._pause.setSingleStep(0.25)
        self._pause.setDecimals(2)
        self._pause.setValue(settings.pause)
        layout.addRow("Задержка:", self._pause)

        # Search depth
        self._search_depth = QSpinBox()
        self._search_depth.setRange(0, 10)
        self._search_depth.setValue(settings.search_depth)
        self._search_depth.setSpecialValueText("Авто")
        self._search_depth.setToolTip("0 = автоматически из сложности, 1-10 = ручная глубина")
        layout.addRow("Глубина поиска:", self._search_depth)

        # Invert color
        self._invert_color = QCheckBox("Играть чёрными")
        self._invert_color.setChecked(settings.invert_color)
        layout.addRow(self._invert_color)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Ок")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setMinimumWidth(280)

    def get_settings(self) -> GameSettings:
        """Return a new GameSettings with values from the dialog controls."""
        s = GameSettings(
            difficulty=self._difficulty.currentIndex() + 1,
            remind=self._remind.isChecked(),
            sound_effect=self._sound.isChecked(),
            pause=self._pause.value(),
            invert_color=self._invert_color.isChecked(),
            search_depth=self._search_depth.value(),
        )
        return s


# ---------------------------------------------------------------------------
# 2. DevelopmentDialog
# ---------------------------------------------------------------------------


class DevelopmentDialog(QDialog):
    """Learning control dialog — choose which outcomes trigger DB updates."""

    def __init__(self, settings: GameSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Развитие")
        self.setModal(True)

        layout = QVBoxLayout(self)

        group = QGroupBox("Предмет развития")
        group_layout = QVBoxLayout(group)

        self._black_win = QCheckBox("Победа чёрных")
        self._black_win.setChecked(settings.black_win)
        group_layout.addWidget(self._black_win)

        self._white_win = QCheckBox("Победа белых")
        self._white_win.setChecked(settings.white_win)
        group_layout.addWidget(self._white_win)

        self._black_lose = QCheckBox("Проигрыш чёрных")
        self._black_lose.setChecked(settings.black_lose)
        group_layout.addWidget(self._black_lose)

        self._white_lose = QCheckBox("Проигрыш белых")
        self._white_lose.setChecked(settings.white_lose)
        group_layout.addWidget(self._white_lose)

        layout.addWidget(group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Ок")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def black_win(self) -> bool:
        return self._black_win.isChecked()

    @property
    def white_win(self) -> bool:
        return self._white_win.isChecked()

    @property
    def black_lose(self) -> bool:
        return self._black_lose.isChecked()

    @property
    def white_lose(self) -> bool:
        return self._white_lose.isChecked()

    def apply_to(self, settings: GameSettings) -> None:
        """Apply the dialog values to an existing GameSettings object."""
        settings.black_win = self.black_win
        settings.white_win = self.white_win
        settings.black_lose = self.black_lose
        settings.white_lose = self.white_lose


# ---------------------------------------------------------------------------
# 3. InfoDialog
# ---------------------------------------------------------------------------


class InfoDialog(QDialog):
    """Scrollable help text dialog loaded from resources/help.txt."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Информация")
        self.setModal(True)

        layout = QVBoxLayout(self)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._text_edit.setText(self._load_help_text())
        layout.addWidget(self._text_edit)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.resize(480, 320)

    @staticmethod
    def _load_help_text() -> str:
        """Load help text from the resources directory."""
        help_path = Path(__file__).parent.parent / "resources" / "help.txt"
        try:
            return help_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            try:
                return help_path.read_text(encoding="cp1251")
            except (FileNotFoundError, UnicodeDecodeError):
                return "(Текст справки не найден)"
        except UnicodeDecodeError:
            try:
                return help_path.read_text(encoding="cp1251")
            except UnicodeDecodeError:
                return "(Ошибка кодировки файла справки)"


# ---------------------------------------------------------------------------
# 4. AboutDialog
# ---------------------------------------------------------------------------


class AboutDialog(QDialog):
    """About the author / program dialog."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Об авторе")
        self.setModal(True)

        layout = QVBoxLayout(self)

        info = QLabel(
            "<h3>Шашки</h3>"
            "<p>Based on original by <b>Andrey Dugin</b> (1998–2000)</p>"
            "<p>Borland Pascal 7.0 → Python / PyQt6</p>"
            "<p>Русские шашки 8×8 с ИИ-противником</p>"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setWordWrap(True)
        layout.addWidget(info)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setMinimumWidth(300)


# ---------------------------------------------------------------------------
# 5. SaveDialog (module-level function)
# ---------------------------------------------------------------------------


def show_save_dialog(parent: QWidget | None = None) -> str | None:
    """Show a native file-save dialog for JSON game files.

    Returns the selected file path, or None if cancelled.
    """
    filepath, _ = QFileDialog.getSaveFileName(
        parent,
        "Сохранить партию",
        "",
        "JSON файлы (*.json);;Все файлы (*)",
    )
    return filepath if filepath else None


# ---------------------------------------------------------------------------
# 6. LoadDialog (module-level function)
# ---------------------------------------------------------------------------


def show_load_dialog(parent: QWidget | None = None) -> str | None:
    """Show a native file-open dialog for JSON game files.

    Returns the selected file path, or None if cancelled.
    """
    filepath, _ = QFileDialog.getOpenFileName(
        parent,
        "Открыть партию",
        "",
        "JSON файлы (*.json);;Все файлы (*)",
    )
    return filepath if filepath else None


# ---------------------------------------------------------------------------
# 7. GameOverDialog
# ---------------------------------------------------------------------------


class GameOverDialog(QDialog):
    """End-of-game dialog — win / lose / draw with replay or exit."""

    RESULT_PLAY_AGAIN = 1
    RESULT_EXIT = 2

    def __init__(
        self,
        message: str,
        parent: QWidget | None = None,
    ):
        """Create the game-over dialog.

        Args:
            message: Display text, e.g. "Вы выиграли!", "Вы проиграли!", "Ничья!"
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Конец игры")
        self.setModal(True)

        self._result_action = self.RESULT_EXIT

        layout = QVBoxLayout(self)

        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = label.font()
        font.setPointSize(14)
        font.setBold(True)
        label.setFont(font)
        layout.addWidget(label)

        btn_layout = QHBoxLayout()

        again_btn = QPushButton("Ещё раз")
        again_btn.clicked.connect(self._on_play_again)
        btn_layout.addWidget(again_btn)

        exit_btn = QPushButton("Выход")
        exit_btn.clicked.connect(self._on_exit)
        btn_layout.addWidget(exit_btn)

        layout.addLayout(btn_layout)

        self.setMinimumWidth(250)

    def _on_play_again(self) -> None:
        self._result_action = self.RESULT_PLAY_AGAIN
        self.accept()

    def _on_exit(self) -> None:
        self._result_action = self.RESULT_EXIT
        self.reject()

    @property
    def result_action(self) -> int:
        """Return RESULT_PLAY_AGAIN or RESULT_EXIT after the dialog closes."""
        return self._result_action


# ---------------------------------------------------------------------------
# 8. ConfirmExitDialog
# ---------------------------------------------------------------------------


class ConfirmExitDialog(QDialog):
    """Exit confirmation dialog — 'Are you sure you want to quit?'"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Выход")
        self.setModal(True)

        layout = QVBoxLayout(self)

        label = QLabel("Вы уверены, что хотите выйти?")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        buttons.button(QDialogButtonBox.StandardButton.Yes).setText("Да")
        buttons.button(QDialogButtonBox.StandardButton.No).setText("Нет")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ---------------------------------------------------------------------------
# 9. ConfiscateWarningDialog
# ---------------------------------------------------------------------------


class ConfiscateWarningDialog(QDialog):
    """Warning shown when the player ignores a mandatory capture.

    Displays which piece must capture.
    """

    def __init__(
        self,
        piece_position: str,
        parent: QWidget | None = None,
    ):
        """Create the confiscation warning.

        Args:
            piece_position: Human-readable position string, e.g. "c3".
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Предупреждение")
        self.setModal(True)

        layout = QVBoxLayout(self)

        msg = QLabel(f"Шашка на <b>{piece_position}</b> должна бить!\nОбязательное взятие.")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        layout.addWidget(msg)

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setMinimumWidth(280)
