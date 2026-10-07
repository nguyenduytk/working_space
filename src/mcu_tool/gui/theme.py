"""Cursor-like dark theme (default) and light alternate."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from mcu_tool.logstyle import LogRole


@dataclass(frozen=True)
class ThemeColors:
    name: str
    window: str
    panel: str
    input: str
    border: str
    text: str
    muted: str
    accent: str
    selection: str
    log_bg: str
    # log roles
    log_default: str
    log_stderr: str
    log_system: str
    log_error: str
    log_warning: str
    log_info: str
    log_success: str
    log_dim: str


DARK = ThemeColors(
    name="dark",
    window="#1e1e1e",
    panel="#252526",
    input="#2d2d2d",
    border="#3c3c3c",
    text="#e6e6e6",
    muted="#9d9d9d",
    accent="#3794ff",
    selection="#264f78",
    log_bg="#0d1117",
    log_default="#e6edf3",
    log_stderr="#ff7b72",
    log_system="#8b949e",
    log_error="#ff6b6b",
    log_warning="#e3b341",
    log_info="#79c0ff",
    log_success="#3fb950",
    log_dim="#6e7681",
)

LIGHT = ThemeColors(
    name="light",
    window="#f3f3f3",
    panel="#ffffff",
    input="#ffffff",
    border="#d0d0d0",
    text="#1e1e1e",
    muted="#6a6a6a",
    accent="#005fb8",
    selection="#cce8ff",
    log_bg="#ffffff",
    log_default="#1e1e1e",
    log_stderr="#a31515",
    log_system="#6a6a6a",
    log_error="#c50f1f",
    log_warning="#9a6700",
    log_info="#0550ae",
    log_success="#1a7f37",
    log_dim="#8b949e",
)

_current = DARK


def current() -> ThemeColors:
    return _current


def log_color(role: LogRole) -> QColor:
    t = _current
    mapping = {
        LogRole.DEFAULT: t.log_default,
        LogRole.STDERR: t.log_stderr,
        LogRole.SYSTEM: t.log_system,
        LogRole.ERROR: t.log_error,
        LogRole.WARNING: t.log_warning,
        LogRole.INFO: t.log_info,
        LogRole.SUCCESS: t.log_success,
        LogRole.DIM: t.log_dim,
    }
    return QColor(mapping.get(role, t.log_default))


def stylesheet(theme: ThemeColors) -> str:
    return f"""
    QWidget {{
        background-color: {theme.window};
        color: {theme.text};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{
        background-color: {theme.window};
    }}
    QToolBar {{
        background: {theme.panel};
        border-bottom: 1px solid {theme.border};
        spacing: 6px;
        padding: 4px;
    }}
    QStatusBar {{
        background: {theme.panel};
        color: {theme.muted};
        border-top: 1px solid {theme.border};
    }}
    QListWidget, QTabWidget::pane, QPlainTextEdit, QLineEdit, QComboBox, QTableWidget {{
        background-color: {theme.input};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 4px;
        selection-background-color: {theme.selection};
        selection-color: {theme.text};
    }}
    QPlainTextEdit#logPane, QPlainTextEdit#serialPane {{
        background-color: {theme.log_bg};
        color: {theme.log_default};
        font-family: "Cascadia Mono", "Consolas", "Courier New", monospace;
        font-size: 12px;
    }}
    QPushButton {{
        background-color: {theme.panel};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 4px;
        padding: 5px 12px;
    }}
    QPushButton:hover {{
        border-color: {theme.accent};
    }}
    QPushButton:pressed {{
        background-color: {theme.selection};
    }}
    QPushButton:disabled {{
        color: {theme.muted};
    }}
    QHeaderView::section {{
        background: {theme.panel};
        color: {theme.muted};
        border: 1px solid {theme.border};
        padding: 4px;
    }}
    QSplitter::handle {{
        background: {theme.border};
    }}
    QTabBar::tab {{
        background: {theme.panel};
        color: {theme.muted};
        padding: 6px 12px;
        border: 1px solid {theme.border};
        border-bottom: none;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        color: {theme.text};
        background: {theme.input};
    }}
    QLabel {{
        color: {theme.text};
        background: transparent;
    }}
    QLabel#muted {{
        color: {theme.muted};
    }}
    """


def apply_theme(app: QApplication, dark: bool = True) -> ThemeColors:
    global _current
    _current = DARK if dark else LIGHT
    theme = _current
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(theme.window))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(theme.input))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.panel))
    palette.setColor(QPalette.ColorRole.Text, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(theme.panel))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(theme.selection))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme.panel))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.muted))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(theme))
    mono = QFont("Cascadia Mono")
    if not mono.exactMatch():
        mono = QFont("Consolas")
    mono.setStyleHint(QFont.StyleHint.Monospace)
    app.setFont(QFont("Segoe UI", 10))
    return theme
