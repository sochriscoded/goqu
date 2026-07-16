"""goqu design system — the single source of truth for colors, fonts, and style.

Direction: **Ledger** — a calm, analyst-grade look. Cool near-black surfaces in
dark, crisp off-white in light, with one refined teal accent. Deliberately
restrained to avoid generic "AI-slop":

- Exactly **one** accent (teal); it appears only on interactive affordances
  (primary buttons, focus rings, selection, tab underline, links). Never
  decorative.
- Semantic **green/red is reserved for numeric data** (gains/losses), never chrome.
- Hairline 1px borders instead of heavy shadows; small radii; a strict spacing scale.
- **Monospaced numerics** (JetBrains Mono) so figures align in a column — the
  finance tell — while prose stays in a clean sans (Noto Sans).

Usage:
    from ui import theme
    theme.apply(app, theme.resolve_mode(pref, app))   # at startup / on toggle
    color = theme.pl_color(value)                       # in populate/refresh code
    theme.theme_signals().theme_changed.connect(view.refresh)

Static styling lives in `build_qss` (keyed off object names / roles), so a theme
switch just swaps the stylesheet + palette. Only per-value data colors are set
from Python, and views re-apply those on their existing `refresh()`.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from string import Template

from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, QObject, Signal

# --- Font stacks (resolve against what's installed; degrade gracefully) --------
SANS = 'Inter, "Noto Sans", "DejaVu Sans", "Segoe UI", "Helvetica Neue", sans-serif'
MONO = '"JetBrains Mono", "JetBrainsMono NF", "DejaVu Sans Mono", "Roboto Mono", monospace'


@dataclass(frozen=True)
class Tokens:
    name: str
    app_bg: str
    sidebar_bg: str
    surface: str        # cards, tiles, panels
    surface_alt: str    # alternating rows, table headers
    hover: str
    border: str
    border_strong: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str    # text/icon on an accent fill
    selection_bg: str
    selection_text: str
    gain: str
    loss: str


DARK = Tokens(
    name="dark",
    app_bg="#0E1116",
    sidebar_bg="#0B0E12",
    surface="#161A21",
    surface_alt="#1B212A",
    hover="#1E2530",
    border="#262D38",
    border_strong="#313A47",
    text_primary="#E6E9EF",
    text_secondary="#9BA6B4",
    text_muted="#6B7686",
    accent="#15B0A6",
    accent_hover="#1DC4B9",
    accent_pressed="#109C93",
    accent_text="#04211D",
    selection_bg="#17313A",
    selection_text="#E6E9EF",
    gain="#16B364",
    loss="#E5484D",
)

LIGHT = Tokens(
    name="light",
    app_bg="#F7F8FA",
    sidebar_bg="#EEF1F4",
    surface="#FFFFFF",
    surface_alt="#F3F5F8",
    hover="#EDF1F5",
    border="#E1E5EA",
    border_strong="#CDD3DB",
    text_primary="#1A1F27",
    text_secondary="#55606E",
    text_muted="#8A94A2",
    accent="#0E8A82",
    accent_hover="#0FA096",
    accent_pressed="#0C726C",
    accent_text="#FFFFFF",
    selection_bg="#D8EFEC",
    selection_text="#10302C",
    gain="#067A3E",
    loss="#C4342B",
)

THEMES: dict[str, Tokens] = {"dark": DARK, "light": LIGHT}

# Active state (set by apply()). Default to dark so accessors work pre-apply.
_active: Tokens = DARK
_mode: str = "dark"


# --- Stylesheet ---------------------------------------------------------------
# $-placeholders (string.Template) so we don't have to escape QSS's own braces.
_QSS = Template(
    """
* { outline: 0; }

QWidget {
    background-color: $app_bg;
    color: $text_primary;
    font-family: $sans;
    selection-background-color: $selection_bg;
    selection-color: $selection_text;
}
QToolTip {
    background-color: $surface_alt;
    color: $text_primary;
    border: 1px solid $border;
    padding: 4px 8px;
}

/* ---- Typographic roles (object names set in the views) ---- */
QLabel { background: transparent; }
QLabel#Title       { font-size: 20px; font-weight: 700; }
QLabel#Subtitle    { color: $text_secondary; }
QLabel#SectionLabel{ color: $text_muted; font-size: 11px; font-weight: 700; }
QLabel#Muted, QLabel#MutedItalic { color: $text_muted; }
QLabel#MutedItalic { font-style: italic; }
QLabel#MetricCaption { color: $text_muted; font-size: 11px; font-weight: 700; }
QLabel#MetricValue   { font-family: $mono; font-size: 22px; font-weight: 700; color: $text_primary; }
QLabel#MetricValue[pl="gain"]  { color: $gain; }
QLabel#MetricValue[pl="loss"]  { color: $loss; }
QLabel#MetricValue[pl="muted"] { color: $text_muted; }
QLabel#DataValue { font-family: $mono; font-weight: 600; }
QLabel#DataValue[pl="gain"]  { color: $gain; }
QLabel#DataValue[pl="loss"]  { color: $loss; }
QLabel#DataValue[pl="muted"] { color: $text_muted; }
QLabel#CardName      { font-size: 15px; font-weight: 700; }
QLabel#CardMeta      { color: $text_secondary; }
QLabel#EmptyText     { color: $text_muted; font-size: 14px; }

/* ---- Left navigation rail ---- */
QListWidget#Sidebar {
    background-color: $sidebar_bg;
    border: none;
    border-right: 1px solid $border;
    padding: 8px 6px;
    outline: 0;
}
QListWidget#Sidebar::item {
    padding: 9px 12px;
    border-radius: 5px;
    color: $text_secondary;
    margin: 1px 2px;
}
QListWidget#Sidebar::item:hover   { background-color: $hover; color: $text_primary; }
QListWidget#Sidebar::item:selected{
    background-color: $surface;
    color: $text_primary;
    border-left: 2px solid $accent;
}

QStackedWidget { background: transparent; }
QSplitter::handle { background-color: $border; width: 1px; }

/* ---- Cards / tiles / panels ---- */
QFrame#Card, QFrame#MetricTile, QFrame#Panel {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 6px;
}
QFrame#Card:hover { border-color: $border_strong; }
QFrame[frameShape="4"] { color: $border; border: none; background: $border; max-height: 1px; }

/* ---- Buttons ---- */
QPushButton {
    background-color: $surface;
    color: $text_primary;
    border: 1px solid $border_strong;
    border-radius: 5px;
    padding: 6px 14px;
    font-weight: 600;
}
QPushButton:hover   { background-color: $hover; border-color: $accent; }
QPushButton:pressed { background-color: $surface_alt; }
QPushButton:disabled{ color: $text_muted; border-color: $border; background-color: $surface; }

QPushButton#PrimaryButton {
    background-color: $accent;
    color: $accent_text;
    border: 1px solid $accent;
}
QPushButton#PrimaryButton:hover   { background-color: $accent_hover; border-color: $accent_hover; }
QPushButton#PrimaryButton:pressed { background-color: $accent_pressed; border-color: $accent_pressed; }

QPushButton#LinkButton, QPushButton:flat {
    background: transparent;
    border: none;
    color: $accent;
    padding: 4px 6px;
    font-weight: 600;
}
QPushButton#LinkButton:hover, QPushButton:flat:hover { color: $accent_hover; }

/* ---- Tables ---- */
QTableView, QTableWidget {
    background-color: $surface;
    alternate-background-color: $surface_alt;
    gridline-color: $border;
    border: 1px solid $border;
    border-radius: 6px;
    font-family: $mono;
    font-size: 13px;
}
QTableView::item { padding: 3px 8px; border: none; }
QTableView::item:selected { background-color: $selection_bg; color: $selection_text; }
QHeaderView { background-color: $surface_alt; }
QHeaderView::section {
    background-color: $surface_alt;
    color: $text_muted;
    font-family: $sans;
    font-weight: 700;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid $border;
}
QTableCornerButton::section { background-color: $surface_alt; border: none; }

/* ---- Tabs ---- */
QTabWidget::pane { border: 1px solid $border; border-radius: 6px; top: -1px; }
QTabBar::tab {
    background: transparent;
    color: $text_secondary;
    padding: 7px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover    { color: $text_primary; }
QTabBar::tab:selected { color: $text_primary; border-bottom: 2px solid $accent; }

/* ---- Inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit {
    background-color: $surface;
    color: $text_primary;
    border: 1px solid $border_strong;
    border-radius: 5px;
    padding: 5px 8px;
    selection-background-color: $selection_bg;
    selection-color: $selection_text;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus,
QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus { border: 1px solid $accent; }
QLineEdit:disabled, QComboBox:disabled { color: $text_muted; background-color: $surface_alt; }

QComboBox::drop-down, QDateEdit::drop-down {
    border: none; width: 20px; subcontrol-position: center right; margin-right: 4px;
}
QComboBox QAbstractItemView {
    background-color: $surface;
    border: 1px solid $border;
    selection-background-color: $selection_bg;
    selection-color: $selection_text;
    outline: 0;
}
QDoubleSpinBox::up-button, QSpinBox::up-button, QDateEdit::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button, QDateEdit::down-button {
    background: $surface_alt; border: none; width: 16px;
}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover { background: $hover; }

/* ---- Menus / status bar ---- */
QMenuBar { background-color: $app_bg; border-bottom: 1px solid $border; }
QMenuBar::item { padding: 6px 10px; background: transparent; }
QMenuBar::item:selected { background-color: $hover; border-radius: 4px; }
QMenu { background-color: $surface; border: 1px solid $border; padding: 4px; }
QMenu::item { padding: 6px 22px 6px 20px; border-radius: 4px; }
QMenu::item:selected { background-color: $selection_bg; color: $selection_text; }
QMenu::separator { height: 1px; background: $border; margin: 4px 8px; }
QStatusBar { background-color: $sidebar_bg; border-top: 1px solid $border; color: $text_muted; }
QStatusBar QLabel#StatusText { color: $text_muted; font-family: $mono; font-size: 11px; }
QStatusBar QLabel#StatusDot  { color: $accent; font-size: 14px; }

/* ---- Scroll areas / bars ---- */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical   { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: $border_strong; border-radius: 5px; min-height: 28px; min-width: 28px;
}
QScrollBar::handle:hover { background: $text_muted; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---- Calendar popup ---- */
QCalendarWidget QWidget { background-color: $surface; }
QCalendarWidget QToolButton { color: $text_primary; background: transparent; }
QCalendarWidget QToolButton:hover { background: $hover; border-radius: 4px; }
QCalendarWidget QAbstractItemView:enabled {
    background: $surface; color: $text_primary;
    selection-background-color: $accent; selection-color: $accent_text;
}

/* ---- Dialogs / wizard ---- */
QDialog, QWizard { background-color: $app_bg; }
QMessageBox { background-color: $surface; }
"""
)


def build_qss(t: Tokens) -> str:
    return _QSS.substitute(sans=SANS, mono=MONO, **asdict(t))


def build_palette(t: Tokens) -> QtGui.QPalette:
    """A matching QPalette so style-drawn bits (tooltips, disabled text, text
    cursor, native selection) agree with the stylesheet."""
    def c(hex_: str) -> QtGui.QColor:
        return QtGui.QColor(hex_)

    p = QtGui.QPalette()
    Role = QtGui.QPalette.ColorRole
    Group = QtGui.QPalette.ColorGroup

    p.setColor(Role.Window, c(t.app_bg))
    p.setColor(Role.WindowText, c(t.text_primary))
    p.setColor(Role.Base, c(t.surface))
    p.setColor(Role.AlternateBase, c(t.surface_alt))
    p.setColor(Role.ToolTipBase, c(t.surface_alt))
    p.setColor(Role.ToolTipText, c(t.text_primary))
    p.setColor(Role.Text, c(t.text_primary))
    p.setColor(Role.PlaceholderText, c(t.text_muted))
    p.setColor(Role.Button, c(t.surface))
    p.setColor(Role.ButtonText, c(t.text_primary))
    p.setColor(Role.BrightText, c(t.loss))
    p.setColor(Role.Link, c(t.accent))
    p.setColor(Role.Highlight, c(t.accent))
    p.setColor(Role.HighlightedText, c(t.accent_text))

    for role in (Role.WindowText, Role.Text, Role.ButtonText):
        p.setColor(Group.Disabled, role, c(t.text_muted))
    return p


# --- Apply / resolve ----------------------------------------------------------

def apply(app: QtWidgets.QApplication, mode: str) -> None:
    """Apply a theme to the whole application and announce the change."""
    global _active, _mode
    tokens = THEMES.get(mode, DARK)
    _active, _mode = tokens, tokens.name

    app.setStyle("Fusion")  # consistent base for QSS across platforms
    app.setPalette(build_palette(tokens))
    app.setStyleSheet(build_qss(tokens))

    font = QtGui.QFont()
    font.setFamilies(["Inter", "Noto Sans", "DejaVu Sans", "Segoe UI"])
    font.setPointSize(10)
    app.setFont(font)

    theme_signals().theme_changed.emit(tokens.name)


def resolve_mode(pref: str, app: QtWidgets.QApplication | None = None) -> str:
    """Map a stored preference ('dark' | 'light' | 'system') to a concrete mode."""
    if pref in THEMES:
        return pref
    if pref == "system" and app is not None:
        scheme = app.styleHints().colorScheme()
        return "light" if scheme == Qt.ColorScheme.Light else "dark"
    return "dark"


# --- Accessors for dynamic (per-value) data colors ----------------------------

def active() -> Tokens:
    return _active


def current_mode() -> str:
    return _mode


def gain() -> QtGui.QColor:
    return QtGui.QColor(_active.gain)


def loss() -> QtGui.QColor:
    return QtGui.QColor(_active.loss)


def muted() -> QtGui.QColor:
    return QtGui.QColor(_active.text_muted)


def text_muted_hex() -> str:
    return _active.text_muted


def pl_color(value) -> QtGui.QColor:
    """Gain/loss/neutral color for a signed number (used for table cells)."""
    if value is None or value == 0:
        return muted()
    return gain() if value > 0 else loss()


def pl_kind(value) -> str:
    """Gain/loss/neutral *category* for a signed number, for the QSS `pl`
    property on metric tiles (so they recolor on a theme swap without a rebuild)."""
    if value is None or value == 0:
        return "muted"
    return "gain" if value > 0 else "loss"


def set_pl_property(label: QtWidgets.QLabel, kind: str | None) -> None:
    """Set the dynamic `pl` property and re-polish so the QSS rule takes effect."""
    label.setProperty("pl", kind or "")
    label.style().unpolish(label)
    label.style().polish(label)


# --- Change signal (mirrors data/events.py's bus pattern) ---------------------

class _ThemeSignals(QObject):
    theme_changed = Signal(str)  # mode name


_signals: _ThemeSignals | None = None


def theme_signals() -> _ThemeSignals:
    global _signals
    if _signals is None:
        _signals = _ThemeSignals()
    return _signals
