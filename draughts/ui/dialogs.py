"""Dialog windows for the draughts application.

All dialogs use standard PyQt6 widgets for a clean, native Windows look.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextDocument
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
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from draughts.config import GameSettings
from draughts.game.ai.elo import ELO_LEVELS

# Re-export from theme.py for backward compat
from draughts.ui.theme import combobox_qss as combobox_qss
from draughts.ui.theme_engine import apply_theme as _apply_engine_theme


def apply_dialog_theme(dialog: QDialog, theme_name: str | None = None) -> None:
    """Apply the project's theme colors to any QDialog.

    Uses the centralized theme engine for consistent styling.
    """
    if theme_name is None:
        theme_name = "dark_wood"
    _apply_engine_theme(dialog, theme_name)


# ---------------------------------------------------------------------------
# 1. OptionsDialog
# ---------------------------------------------------------------------------


class OptionsDialog(QDialog):
    """Settings dialog -- tabbed layout (D15).

    Tab 1: Игра      -- side, Elo level, mandatory-capture hint
    Tab 2: Движок    -- hash size, threads (stub), opening book (stub),
                       endgame bitbase (stub), depth override (dev)
    Tab 3: Интерфейс -- animation speed, coordinates, last-move highlight,
                       show legal moves on hover
    Tab 4: Анализ    -- stub placeholder for M3 analysis features
    """

    def __init__(self, settings: GameSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Опции")
        self.setModal(True)

        self._settings = settings
        self._dev_mode: bool = getattr(settings, "dev_mode", False)

        # Apply theme-aware stylesheet via the theme engine
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
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Ок")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.setMinimumWidth(400)

    def _apply_dialog_theme(self, theme_name: str) -> None:
        _apply_engine_theme(self, theme_name)

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
            "<i>По правилам русских шашек взятие обязательно.<br>При нарушении шашка противника конфискуется.</i>"
        )
        rule_label.setWordWrap(True)
        rule_label.setTextFormat(Qt.TextFormat.RichText)
        form.addRow(rule_label)

        return page

    def _build_engine_tab(self, s: GameSettings) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        # Hash size (MB) — read at AIEngine construction via
        # ``hash_size_mb``; since the engine is recreated for each
        # AI turn, the new value applies from the very next move.
        self._hash_size = QSpinBox()
        self._hash_size.setRange(4, 1024)
        self._hash_size.setSuffix(" МБ")
        self._hash_size.setValue(getattr(s, "hash_size_mb", 32))
        self._hash_size.setToolTip(
            "Размер таблицы транспозиций. Новое значение применяется "
            "со следующего хода компьютера."
        )
        form.addRow("Хэш-таблица:", self._hash_size)

        # Threads — stub, always 1, disabled
        self._threads = QSpinBox()
        self._threads.setRange(1, 1)
        self._threads.setValue(1)
        # STUB(M5): SMP не реализовано, включить при реализации многопоточного поиска
        self._threads.setEnabled(False)
        self._threads.setToolTip("Многопоточный поиск (планируется в будущих версиях)")
        form.addRow("Потоки:", self._threads)

        # Opening book (D8)
        self._opening_book = QCheckBox("Дебютная книга")
        self._opening_book.setChecked(s.use_opening_book)
        self._opening_book.setToolTip("Использовать книгу дебютов для первых ходов")
        form.addRow(self._opening_book)

        # Endgame bitbase (D9)
        self._bitbase = QCheckBox("Эндшпильная база")
        self._bitbase.setChecked(s.use_endgame_bitbase)
        self._bitbase.setToolTip("Использовать базу эндшпилей для точной игры в окончаниях")
        form.addRow(self._bitbase)

        # Depth override — only enabled in dev mode
        self._search_depth = QSpinBox()
        self._search_depth.setRange(0, 16)
        self._search_depth.setValue(s.search_depth)
        self._search_depth.setSpecialValueText("Авто")
        self._search_depth.setToolTip("0 = автоматически из уровня, 1-16 = принудительная глубина (dev)")
        self._search_depth.setEnabled(self._dev_mode)
        lbl = QLabel("Глубина (dev):")
        lbl.setEnabled(self._dev_mode)
        form.addRow(lbl, self._search_depth)

        return page

    def _build_ui_tab(self, s: GameSettings) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        # Board theme selector (D18) — dynamically populated from theme files
        from draughts.ui.theme_engine import get_theme as _get_theme
        from draughts.ui.theme_engine import list_themes

        self._board_theme = QComboBox()
        for theme_stem in list_themes():
            try:
                t = _get_theme(theme_stem)
                self._board_theme.addItem(t.display_name, userData=theme_stem)
            except Exception:
                self._board_theme.addItem(theme_stem, userData=theme_stem)
        # Fallback: ensure at least the two built-in themes are listed
        if self._board_theme.count() == 0:
            self._board_theme.addItem("Тёмное дерево", userData="dark_wood")
            self._board_theme.addItem("Классическая светлая", userData="classic_light")
        current_theme = getattr(s, "board_theme", "dark_wood")
        theme_idx = self._board_theme.findData(current_theme)
        if theme_idx >= 0:
            self._board_theme.setCurrentIndex(theme_idx)
        # Live preview: apply theme immediately on selection change
        self._board_theme.currentIndexChanged.connect(self._on_theme_preview)
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

        return page

    def _on_theme_preview(self, _index: int) -> None:
        """Live-preview the selected theme on this dialog."""
        theme_stem = self._board_theme.currentData() or "dark_wood"
        self._apply_dialog_theme(theme_stem)
        # Also propagate to the parent main window for instant feedback
        parent = self.parent()
        if parent is not None and hasattr(parent, "_apply_theme"):
            parent._apply_theme(theme_stem)

    def _build_analysis_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        info = QLabel(
            "<b>Панель анализа</b> — F3 или меню Анализ<br>"
            "<b>Анализ партии</b> — меню Анализ → Проанализировать партию<br><br>"
            "Настройки анализа будут добавлены в будущих версиях."
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        layout.addWidget(info)

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
            hash_size_mb=self._hash_size.value(),
            use_opening_book=self._opening_book.isChecked(),
            use_endgame_bitbase=self._bitbase.isChecked(),
            use_tuned_eval=self._settings.use_tuned_eval,
        )
        return s


# ---------------------------------------------------------------------------
# 2. InfoDialog
# ---------------------------------------------------------------------------


class InfoDialog(QDialog):
    """Scrollable help dialog rendered from resources/help.md.

    Uses Qt6's built-in CommonMark + GFM Markdown parser (md4c) via
    ``QTextDocument.setMarkdown(..., MarkdownDialectGitHub)`` — zero
    extra dependencies. Falls back to the pre-4.1.0 plain-text
    ``help.txt`` if the Markdown file is missing (belt-and-braces for
    downgrade / source checkouts without the new asset).
    """

    def __init__(self, parent: QWidget | None = None, theme: str = "dark_wood"):
        super().__init__(parent)
        self.setWindowTitle("Информация")
        self.setModal(True)
        # QDialog по умолчанию прячет min/max-кнопки. Для справки
        # пользователю удобно развернуть окно на весь экран и читать
        # широкие таблицы (хоткеи, меню, уровни Elo) без прокрутки —
        # вернём штатную рамку с обеими кнопками title-bar'а.
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        apply_dialog_theme(self, theme)

        layout = QVBoxLayout(self)

        # QTextBrowser rather than QTextEdit so hyperlinks in help.md
        # (if we add any later) open in an external browser rather than
        # inside the dialog.
        self._text_browser = QTextBrowser()
        self._text_browser.setReadOnly(True)
        self._text_browser.setOpenExternalLinks(True)
        self._populate(theme)
        layout.addWidget(self._text_browser)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Larger default: Markdown tables + headings benefit from
        # horizontal room. User can still resize manually or maximise.
        self.resize(720, 560)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _populate(self, theme: str) -> None:
        """Load help.md and render it into the document.

        Resolved path order:
          1. resources/help.md  (CommonMark + GFM tables)
          2. resources/help.txt (legacy plain-text, UTF-8 or CP1251)
        """
        md_path = Path(__file__).parent.parent / "resources" / "help.md"
        if md_path.is_file():
            try:
                text = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                text = self._load_legacy_help_text()
            doc = self._text_browser.document()
            doc.setDefaultStyleSheet(self._theme_css(theme))
            # GitHub dialect buys GFM-style tables (used in the rewrite);
            # plain CommonMark would render them as raw text.
            doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
            return

        # No help.md — fall back to legacy text with no formatting.
        self._text_browser.setPlainText(self._load_legacy_help_text())

    @staticmethod
    def _theme_css(theme: str) -> str:
        """Qt-subset CSS so Markdown headings / code / tables track the theme.

        ``QTextDocument.setDefaultStyleSheet`` accepts a limited CSS 2.1
        subset: selectors by tag name, ``color``, ``background-color``,
        ``font-weight``, ``margin``; no classes, no pseudo-selectors.
        See Qt's "Supported HTML Subset" page.
        """
        from draughts.ui.theme_engine import get_theme_colors

        tc = get_theme_colors(theme)
        # Theme palettes expose semantic keys — fg_accent for headings,
        # scroll_bg for code blocks. Fall back to sane defaults if a
        # theme omits the key.
        heading = tc.get("fg_accent", "#d7b37a")
        code_bg = tc.get("scroll_bg", "#2a2421")
        code_fg = tc.get("ann_normal", "#e6e1d4")
        link = tc.get("ann_good", "#6db46d")
        rule = tc.get("ann_move_num", "#7a6a55")
        return (
            f"h1 {{ color: {heading}; font-size: 18pt; }}"
            f"h2 {{ color: {heading}; font-size: 14pt; }}"
            f"h3 {{ color: {heading}; font-size: 12pt; }}"
            f"code {{ background-color: {code_bg}; color: {code_fg}; }}"
            f"pre  {{ background-color: {code_bg}; color: {code_fg}; }}"
            f"a    {{ color: {link}; }}"
            f"th   {{ color: {heading}; }}"
            f"hr   {{ color: {rule}; }}"
        )

    @staticmethod
    def _load_legacy_help_text() -> str:
        """Fallback loader for the pre-4.1 plain-text help.txt."""
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

        import draughts
        from draughts.config import APP_NAME

        info = QLabel(
            f"<h3>{APP_NAME} v{draughts.__version__}</h3>"
            f"<p>Based on original by <b>{draughts.__author__}</b> (1998–2000)</p>"
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
