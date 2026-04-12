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
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from draughts.config import GameSettings
from draughts.game.ai.elo import ELO_LEVELS

# ---------------------------------------------------------------------------
# Shared theme-aware styling for ALL dialogs
# ---------------------------------------------------------------------------

_DIALOG_PALETTES = {
    "dark_wood": {
        "bg": "#2a1a0a", "fg": "#d4b483",
        "border": "#6a4520", "hover": "#5a3d20",
        "input_bg": "#3a2a1a", "btn_bg": "#3a2510",
    },
    "classic_light": {
        "bg": "#f5ead0", "fg": "#3a2a1a",
        "border": "#b8a888", "hover": "#d4c4a4",
        "input_bg": "#ffffff", "btn_bg": "#e0d4b8",
    },
}


def _get_current_theme() -> str:
    """Best-effort read of the active board theme for dialog styling."""
    try:
        # If a GameSettings instance is accessible, use it; otherwise default.
        return "dark_wood"  # caller overrides via apply_dialog_theme
    except Exception:
        return "dark_wood"


def apply_dialog_theme(dialog: QDialog, theme_name: str | None = None) -> None:
    """Apply the project's theme colors to any QDialog.

    Keeps all dialogs (Options, About, GameOver, etc.) visually
    consistent with the main window and puzzle trainer.
    """
    if theme_name is None:
        theme_name = "dark_wood"
    t = _DIALOG_PALETTES.get(theme_name, _DIALOG_PALETTES["dark_wood"])
    dialog.setStyleSheet(
        f"QDialog {{ background: {t['bg']}; color: {t['fg']}; }}"
        f"QLabel {{ color: {t['fg']}; }}"
        f"QTextEdit {{ background: {t['input_bg']}; color: {t['fg']};"
        f"  border: 1px solid {t['border']}; }}"
        f"QPushButton {{ background: {t['btn_bg']}; color: {t['fg']};"
        f"  border: 1px solid {t['border']}; border-radius: 3px;"
        f"  padding: 5px 16px; }}"
        f"QPushButton:hover {{ background: {t['hover']}; }}"
        f"QDialogButtonBox QPushButton {{ min-width: 70px; }}"
    )


# ---------------------------------------------------------------------------
# 1. OptionsDialog
# ---------------------------------------------------------------------------


class OptionsDialog(QDialog):
    """Settings dialog — tabbed layout (D15).

    Tab 1: Игра      — side, Elo level, mandatory-capture hint
    Tab 2: Движок    — hash size, threads (stub), opening book (stub),
                       endgame bitbase (stub), depth override (dev)
    Tab 3: Интерфейс — animation speed, coordinates, last-move highlight,
                       show legal moves on hover
    Tab 4: Анализ    — stub placeholder for M3 analysis features
    """

    # Theme palettes matching main_window._THEMES
    _DIALOG_THEMES = {
        "dark_wood": {
            "bg": "#2a1a0a", "fg": "#d4b483",
            "tab_bg": "#3a2510", "tab_sel": "#4a3520", "tab_border": "#6a4520",
            "input_bg": "#3a2a1a", "input_border": "#5a4a3a",
            "btn_bg": "#3a2510", "btn_hover": "#5a3d20", "btn_border": "#6a4520",
            "hint_fg": "#a08a60", "check_accent": "#d4b483",
        },
        "classic_light": {
            "bg": "#f5ead0", "fg": "#3a2a1a",
            "tab_bg": "#e8dcc0", "tab_sel": "#d4c4a4", "tab_border": "#b8a888",
            "input_bg": "#ffffff", "input_border": "#c8b898",
            "btn_bg": "#e0d4b8", "btn_hover": "#d0c4a4", "btn_border": "#b0a080",
            "hint_fg": "#7a6a4a", "check_accent": "#6a4a2a",
        },
    }

    def __init__(self, settings: GameSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Опции")
        self.setModal(True)

        self._settings = settings
        self._dev_mode: bool = getattr(settings, "dev_mode", False)

        # Apply theme-aware stylesheet
        theme = getattr(settings, "board_theme", "dark_wood")
        self._apply_dialog_theme(theme)

        outer = QVBoxLayout(self)

        tabs = QTabWidget()
        outer.addWidget(tabs)

        tabs.addTab(self._build_game_tab(settings), "Игра")
        tabs.addTab(self._build_engine_tab(settings), "Движок")
        tabs.addTab(self._build_ui_tab(settings), "Интерфейс")
        tabs.addTab(self._build_analysis_tab(), "Анализ")

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Ок")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.setMinimumWidth(400)

    def _apply_dialog_theme(self, theme_name: str) -> None:
        t = self._DIALOG_THEMES.get(theme_name, self._DIALOG_THEMES["dark_wood"])
        # SVG icons for styled checkmarks and radio dots
        res = Path(__file__).parent.parent / "resources"
        suffix = "dark" if theme_name == "dark_wood" else "light"
        check_svg = (res / f"check_{suffix}.svg").as_posix()
        radio_svg = (res / f"radio_{suffix}.svg").as_posix()
        self.setStyleSheet(
            f"QDialog {{ background: {t['bg']}; color: {t['fg']}; }}"
            f"QTabWidget::pane {{ background: {t['bg']};"
            f"  border: 1px solid {t['tab_border']}; }}"
            f"QTabBar::tab {{ background: {t['tab_bg']}; color: {t['fg']};"
            f"  padding: 6px 14px; border: 1px solid {t['tab_border']};"
            f"  border-bottom: none; border-top-left-radius: 4px;"
            f"  border-top-right-radius: 4px; margin-right: 2px; }}"
            f"QTabBar::tab:selected {{ background: {t['tab_sel']};"
            f"  font-weight: bold; }}"
            f"QComboBox {{ background: {t['input_bg']}; color: {t['fg']};"
            f"  border: 1px solid {t['input_border']}; padding: 4px 8px;"
            f"  border-radius: 3px; }}"
            f"QComboBox QAbstractItemView {{ background: {t['input_bg']};"
            f"  color: {t['fg']}; selection-background-color: {t['tab_sel']}; }}"
            f"QComboBox::drop-down {{ subcontrol-origin: padding;"
            f"  subcontrol-position: center right; width: 22px; }}"
            f"QSpinBox {{ background: {t['input_bg']}; color: {t['fg']};"
            f"  border: 1px solid {t['input_border']}; padding: 3px;"
            f"  border-radius: 3px; }}"
            f"QCheckBox {{ color: {t['fg']}; spacing: 6px; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px;"
            f"  background: {t['input_bg']}; border: 2px solid {t['input_border']};"
            f"  border-radius: 3px; }}"
            f"QCheckBox::indicator:checked {{ border-color: {t['check_accent']};"
            f"  image: url({check_svg}); }}"
            f"QRadioButton {{ color: {t['fg']}; spacing: 6px; }}"
            f"QRadioButton::indicator {{ width: 16px; height: 16px;"
            f"  background: {t['input_bg']}; border: 2px solid {t['input_border']};"
            f"  border-radius: 9px; }}"
            f"QRadioButton::indicator:checked {{ border-color: {t['check_accent']};"
            f"  image: url({radio_svg}); }}"
            f"QLabel {{ color: {t['fg']}; }}"
            f"QGroupBox {{ color: {t['fg']}; border: 1px solid {t['tab_border']};"
            f"  border-radius: 4px; margin-top: 8px; padding-top: 12px; }}"
            f"QGroupBox::title {{ color: {t['fg']}; }}"
            f"QPushButton {{ background: {t['btn_bg']}; color: {t['fg']};"
            f"  border: 1px solid {t['btn_border']}; border-radius: 3px;"
            f"  padding: 5px 16px; }}"
            f"QPushButton:hover {{ background: {t['btn_hover']}; }}"
            f"QDialogButtonBox QPushButton {{ min-width: 70px; }}"
        )

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_game_tab(self, s: GameSettings) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        # Side — radio-style via combobox (keeps layout compact)
        self._side = QComboBox()
        self._side.addItem("Белые")
        self._side.addItem("Чёрные")
        self._side.setCurrentIndex(1 if s.invert_color else 0)
        form.addRow("Сторона:", self._side)

        # Elo level — combobox populated from ELO_LEVELS
        self._difficulty = QComboBox()
        for lvl in sorted(ELO_LEVELS):
            self._difficulty.addItem(ELO_LEVELS[lvl]["label"])
        # clamp to valid range
        idx = max(0, min(len(ELO_LEVELS) - 1, s.difficulty - 1))
        self._difficulty.setCurrentIndex(idx)
        form.addRow("Уровень:", self._difficulty)

        # Mandatory-capture hint
        self._remind = QCheckBox("Подсказывать обязательное взятие")
        self._remind.setChecked(s.remind)
        form.addRow(self._remind)

        # Informational note about mandatory-capture rule
        rule_label = QLabel(
            "<i>По правилам русских шашек взятие обязательно.<br>"
            "При нарушении шашка противника конфискуется.</i>"
        )
        rule_label.setWordWrap(True)
        rule_label.setTextFormat(Qt.TextFormat.RichText)
        form.addRow(rule_label)

        return page

    def _build_engine_tab(self, s: GameSettings) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        # Hash size (MB) — wired to settings, TT resize not yet implemented
        self._hash_size = QSpinBox()
        self._hash_size.setRange(4, 1024)
        self._hash_size.setSuffix(" МБ")
        self._hash_size.setValue(getattr(s, "hash_size_mb", 32))
        self._hash_size.setToolTip(
            "Размер таблицы транспозиций. "
            "Изменение вступит в силу в следующей партии."
        )
        form.addRow("Хэш-таблица:", self._hash_size)

        # Threads — stub, always 1, disabled
        self._threads = QSpinBox()
        self._threads.setRange(1, 1)
        self._threads.setValue(1)
        self._threads.setEnabled(False)
        self._threads.setToolTip("Многопоточность (не реализована)")
        form.addRow("Потоки:", self._threads)

        # Opening book — stub, disabled
        self._opening_book = QCheckBox("Дебютная книга")
        self._opening_book.setChecked(False)
        self._opening_book.setEnabled(False)
        self._opening_book.setToolTip("Не реализовано (планируется в M2)")
        form.addRow(self._opening_book)

        # Endgame bitbase — stub, disabled
        self._bitbase = QCheckBox("Эндшпильная база")
        self._bitbase.setChecked(False)
        self._bitbase.setEnabled(False)
        self._bitbase.setToolTip("Не реализовано (планируется в M2)")
        form.addRow(self._bitbase)

        # Depth override — only enabled in dev mode
        self._search_depth = QSpinBox()
        self._search_depth.setRange(0, 16)
        self._search_depth.setValue(s.search_depth)
        self._search_depth.setSpecialValueText("Авто")
        self._search_depth.setToolTip(
            "0 = автоматически из уровня, 1-16 = принудительная глубина (dev)"
        )
        self._search_depth.setEnabled(self._dev_mode)
        lbl = QLabel("Глубина (dev):")
        lbl.setEnabled(self._dev_mode)
        form.addRow(lbl, self._search_depth)

        return page

    def _build_ui_tab(self, s: GameSettings) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        # Board theme selector (D18)
        self._board_theme = QComboBox()
        self._board_theme.addItem("Тёмное дерево", userData="dark_wood")
        self._board_theme.addItem("Классическая светлая", userData="classic_light")
        current_theme = getattr(s, "board_theme", "dark_wood")
        theme_idx = self._board_theme.findData(current_theme)
        if theme_idx >= 0:
            self._board_theme.setCurrentIndex(theme_idx)
        form.addRow("Тема доски:", self._board_theme)

        # Animation speed slider (maps pause 0.0-2.0 to slider 0-8)
        self._anim_slider = QSlider(Qt.Orientation.Horizontal)
        self._anim_slider.setRange(0, 8)
        self._anim_slider.setTickInterval(1)
        self._anim_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider_val = round(s.pause / 0.25)
        self._anim_slider.setValue(max(0, min(8, slider_val)))
        self._anim_slider.setToolTip("0 = без анимации, 8 = медленно (пауза 2 с)")
        form.addRow("Скорость анимации:", self._anim_slider)

        # Show coordinates
        self._show_coords = QCheckBox("Показывать координаты")
        self._show_coords.setChecked(getattr(s, "show_coordinates", False))
        form.addRow(self._show_coords)

        # Highlight last move
        self._highlight_last = QCheckBox("Подсвечивать последний ход")
        self._highlight_last.setChecked(getattr(s, "highlight_last_move", True))
        form.addRow(self._highlight_last)

        # Show legal moves on hover
        self._show_legal = QCheckBox("Показывать возможные ходы при наведении")
        self._show_legal.setChecked(getattr(s, "show_legal_moves_hover", False))
        form.addRow(self._show_legal)

        # Clock display (D19)
        self._show_clock = QCheckBox("Показывать затраченное время сторон")
        self._show_clock.setChecked(getattr(s, "show_clock", False))
        self._show_clock.setToolTip("Отображает суммарное время обдумывания каждой стороны")
        form.addRow(self._show_clock)

        return page

    def _build_analysis_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        coming_soon = QLabel(
            "<h3>Анализ партии</h3>"
            "<p>Функции анализа (оценка позиции, аннотации ходов,<br>"
            "график оценки) будут доступны в следующем обновлении (M3).</p>"
        )
        coming_soon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        coming_soon.setTextFormat(Qt.TextFormat.RichText)
        coming_soon.setWordWrap(True)
        layout.addWidget(coming_soon)

        return page

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def get_settings(self) -> GameSettings:
        """Return a new GameSettings populated from all tab controls."""
        pause_val = round(self._anim_slider.value() * 0.25, 2)
        board_theme = self._board_theme.currentData() or "dark_wood"
        s = GameSettings(
            difficulty=self._difficulty.currentIndex() + 1,
            remind=self._remind.isChecked(),
            pause=pause_val,
            invert_color=(self._side.currentIndex() == 1),
            search_depth=self._search_depth.value(),
            board_theme=board_theme,
            show_coordinates=self._show_coords.isChecked(),
            highlight_last_move=self._highlight_last.isChecked(),
            show_legal_moves_hover=self._show_legal.isChecked(),
            show_clock=self._show_clock.isChecked(),
            hash_size_mb=self._hash_size.value(),
        )
        return s


# ---------------------------------------------------------------------------
# 2. InfoDialog
# ---------------------------------------------------------------------------


class InfoDialog(QDialog):
    """Scrollable help text dialog loaded from resources/help.txt."""

    def __init__(self, parent: QWidget | None = None, theme: str = "dark_wood"):
        super().__init__(parent)
        self.setWindowTitle("Информация")
        self.setModal(True)
        apply_dialog_theme(self, theme)

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

    def __init__(self, parent: QWidget | None = None, theme: str = "dark_wood"):
        super().__init__(parent)
        self.setWindowTitle("Об авторе")
        self.setModal(True)
        apply_dialog_theme(self, theme)

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
    """Show a native file-save dialog.

    PDN is the default format; JSON is offered for backward compatibility.
    Returns the selected file path (with extension), or None if cancelled.
    """
    filepath, selected_filter = QFileDialog.getSaveFileName(
        parent,
        "Сохранить партию",
        "",
        "PDN файлы (*.pdn);;JSON файлы (*.json);;Все файлы (*)",
    )
    if not filepath:
        return None
    # Ensure correct extension based on chosen filter
    from pathlib import Path as _Path
    p = _Path(filepath)
    if not p.suffix and "PDN" in selected_filter:
        filepath = filepath + ".pdn"
    elif not p.suffix and "JSON" in selected_filter:
        filepath = filepath + ".json"
    return filepath


# ---------------------------------------------------------------------------
# 6. LoadDialog (module-level function)
# ---------------------------------------------------------------------------


def show_load_dialog(parent: QWidget | None = None) -> str | None:
    """Show a native file-open dialog.

    PDN is the primary format; JSON legacy saves are also accepted.
    Returns the selected file path, or None if cancelled.
    """
    filepath, _ = QFileDialog.getOpenFileName(
        parent,
        "Открыть партию",
        "",
        "Файлы партий (*.pdn *.json);;PDN файлы (*.pdn);;JSON файлы (*.json);;Все файлы (*)",
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
        theme: str = "dark_wood",
    ):
        """Create the game-over dialog.

        Args:
            message: Display text, e.g. "Вы выиграли!", "Вы проиграли!", "Ничья!"
            parent: Parent widget.
            theme: Board theme name for consistent dialog styling.
        """
        super().__init__(parent)
        self.setWindowTitle("Конец игры")
        self.setModal(True)
        apply_dialog_theme(self, theme)

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

    def __init__(self, parent: QWidget | None = None, theme: str = "dark_wood"):
        super().__init__(parent)
        self.setWindowTitle("Выход")
        self.setModal(True)
        apply_dialog_theme(self, theme)

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
        theme: str = "dark_wood",
    ):
        """Create the confiscation warning.

        Args:
            piece_position: Human-readable position string, e.g. "c3".
            parent: Parent widget.
            theme: Board theme name for styling.
        """
        super().__init__(parent)
        apply_dialog_theme(self, theme)
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
