"""Tema escuro do aplicativo: paleta, fonte e folha de estilo (QSS)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication


class Colors:
    BACKGROUND = "#111318"
    SURFACE = "#1A1D24"         # cartões, campos
    SURFACE_HOVER = "#212530"
    SURFACE_RAISED = "#232833"  # botões
    SURFACE_SELECTED = "#2A2544"
    BORDER = "#2A2F3A"
    BORDER_STRONG = "#363C4A"
    TEXT = "#E7E9EE"
    TEXT_SECONDARY = "#9AA3B2"
    TEXT_MUTED = "#5F6776"
    LYRICS_DIM = "#858E9E"      # versos que não estão sendo cantados
    ACCENT = "#8B5CF6"          # violeta
    ACCENT_HOVER = "#A07BFA"
    ACCENT_PRESSED = "#7444E8"
    ACCENT_DIM = "#3A2F63"
    SUCCESS = "#22C55E"
    WARNING = "#F59E0B"
    INFO = "#38BDF8"
    DANGER = "#EF4444"


FONT_FAMILIES = ["Inter", "Noto Sans", "Cantarell", "Ubuntu", "DejaVu Sans"]
BASE_FONT_SIZE = 11  # pt


def color(hex_code: str, alpha: int = 255) -> QColor:
    c = QColor(hex_code)
    c.setAlpha(alpha)
    return c


def _palette() -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: Colors.BACKGROUND,
        QPalette.ColorRole.WindowText: Colors.TEXT,
        QPalette.ColorRole.Base: Colors.SURFACE,
        QPalette.ColorRole.AlternateBase: Colors.SURFACE_HOVER,
        QPalette.ColorRole.Text: Colors.TEXT,
        QPalette.ColorRole.PlaceholderText: Colors.TEXT_MUTED,
        QPalette.ColorRole.Button: Colors.SURFACE_RAISED,
        QPalette.ColorRole.ButtonText: Colors.TEXT,
        QPalette.ColorRole.Highlight: Colors.ACCENT,
        QPalette.ColorRole.HighlightedText: "#FFFFFF",
        QPalette.ColorRole.ToolTipBase: Colors.SURFACE,
        QPalette.ColorRole.ToolTipText: Colors.TEXT,
        QPalette.ColorRole.Link: Colors.ACCENT_HOVER,
        QPalette.ColorRole.BrightText: "#FFFFFF",
    }
    for role, value in roles.items():
        p.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(Colors.TEXT_MUTED))
    return p


STYLESHEET = f"""
* {{
    outline: 0;
}}
QMainWindow, QDialog, QWidget#playerWindow {{
    background: {Colors.BACKGROUND};
}}
QToolTip {{
    background: {Colors.SURFACE};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ---- títulos ---- */
QLabel#appTitle {{
    font-size: 20pt;
    font-weight: 700;
    color: {Colors.TEXT};
}}
QLabel#appSubtitle, QLabel#hint {{
    color: {Colors.TEXT_SECONDARY};
}}
QLabel#sectionHeader {{
    color: {Colors.TEXT_SECONDARY};
    font-weight: 600;
    font-size: 10pt;
    letter-spacing: 1px;
    padding: 4px 2px 2px 2px;
}}
QLabel#songTitle {{
    font-size: 20pt;
    font-weight: 700;
}}

/* ---- campos ---- */
QLineEdit, QPlainTextEdit {{
    background: {Colors.SURFACE};
    border: 1px solid {Colors.BORDER};
    border-radius: 10px;
    padding: 8px 12px;
    selection-background-color: {Colors.ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {Colors.ACCENT};
}}
QLineEdit#urlBar {{
    border-radius: 14px;
    padding: 12px 18px;
    font-size: 12pt;
}}
QLineEdit#filterBar {{
    border-radius: 10px;
    padding: 5px 10px 5px 4px;
}}

/* ---- botões ---- */
QPushButton {{
    background: {Colors.SURFACE_RAISED};
    border: 1px solid {Colors.BORDER_STRONG};
    border-radius: 10px;
    padding: 9px 18px;
    min-height: 22px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {Colors.SURFACE_HOVER};
    border-color: {Colors.TEXT_MUTED};
}}
QPushButton:pressed {{
    background: {Colors.SURFACE};
}}
QPushButton:disabled {{
    color: {Colors.TEXT_MUTED};
    border-color: {Colors.BORDER};
}}
QPushButton:checked {{
    background: {Colors.ACCENT_DIM};
    border-color: {Colors.ACCENT};
}}
QPushButton:default, QPushButton#primary {{
    background: {Colors.ACCENT};
    border: 1px solid {Colors.ACCENT};
    color: #FFFFFF;
}}
QPushButton:default:hover, QPushButton#primary:hover {{
    background: {Colors.ACCENT_HOVER};
}}
QPushButton:default:disabled, QPushButton#primary:disabled {{
    background: {Colors.ACCENT_DIM};
    border-color: {Colors.ACCENT_DIM};
    color: {Colors.TEXT_SECONDARY};
}}
QPushButton#fontButton {{
    padding: 0;
    font-size: 12pt;
    font-weight: 700;
    border-radius: 10px;
}}
QPushButton:focus {{
    border: 2px solid {Colors.ACCENT_HOVER};
}}
QPushButton:default:focus, QPushButton#primary:focus {{
    border: 2px solid #FFFFFF;
}}
QPushButton#playButton {{
    background: {Colors.ACCENT};
    border: none;
    border-radius: 28px;
    min-width: 56px; max-width: 56px;
    min-height: 56px; max-height: 56px;
    padding: 0;
}}
QPushButton#playButton:hover {{
    background: {Colors.ACCENT_HOVER};
}}
QPushButton#playButton:pressed {{
    background: {Colors.ACCENT_PRESSED};
}}
QPushButton#playButton:focus {{
    border: 3px solid #FFFFFF;
}}
QPushButton#playButton:disabled {{
    background: {Colors.ACCENT_DIM};
}}

/* ---- listas e tabelas ---- */
QListView {{
    background: transparent;
    border: none;
}}
QListWidget#lyrics, QListWidget#lyrics > QWidget {{
    background: transparent;
    border: none;
}}
QTableWidget {{
    background: {Colors.SURFACE};
    border: 1px solid {Colors.BORDER};
    border-radius: 10px;
    gridline-color: {Colors.BORDER};
    selection-background-color: {Colors.ACCENT_DIM};
    selection-color: {Colors.TEXT};
}}
QTableWidget::item {{
    padding: 6px;
}}
QTableWidget:focus {{
    border: 1px solid {Colors.ACCENT};
}}
QHeaderView::section {{
    background: {Colors.SURFACE_RAISED};
    color: {Colors.TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {Colors.BORDER};
    padding: 8px;
    font-weight: 600;
}}

/* ---- resultados do YouTube ---- */
QListWidget#results {{
    background: transparent;
    border: none;
}}
QListWidget#results::item {{
    background: {Colors.SURFACE};
    border: 1px solid {Colors.BORDER};
    border-radius: 12px;
}}
QListWidget#results::item:hover {{
    background: {Colors.SURFACE_HOVER};
}}
QListWidget#results::item:selected {{
    background: {Colors.SURFACE_SELECTED};
    border: 1px solid {Colors.ACCENT};
}}
QLabel#resultTitle {{
    font-size: 12pt;
    font-weight: 600;
    background: transparent;
}}
QLabel#thumbnail {{
    background: {Colors.SURFACE_RAISED};
    border-radius: 8px;
}}

/* ---- cartões ---- */
QFrame#card {{
    background: rgba(26, 29, 36, 225);
    border: 1px solid {Colors.BORDER};
    border-radius: 16px;
}}
QFrame#card QLabel {{
    background: transparent;
}}

/* ---- sliders e progresso ---- */
QSlider::groove:horizontal {{
    height: 6px;
    background: {Colors.BORDER_STRONG};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {Colors.ACCENT};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #FFFFFF;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:focus {{
    background: {Colors.ACCENT_HOVER};
    border: 2px solid #FFFFFF;
}}
QSlider::handle:horizontal:hover {{
    background: {Colors.ACCENT_HOVER};
}}
QSlider::sub-page:horizontal:disabled {{
    background: {Colors.TEXT_MUTED};
}}
QProgressBar {{
    background: {Colors.BORDER_STRONG};
    border: none;
    border-radius: 4px;
    max-height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {Colors.ACCENT};
    border-radius: 4px;
}}

/* ---- barra de status, divisórias, rolagem, menus ---- */
QStatusBar {{
    background: {Colors.SURFACE};
    color: {Colors.TEXT_SECONDARY};
    border-top: 1px solid {Colors.BORDER};
    padding: 4px 8px;
}}
QStatusBar::item {{
    border: none;
}}
QSplitter::handle {{
    background: transparent;  /* a alça é desenhada por views/splitter.py */
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {Colors.BORDER_STRONG};
    border-radius: 4px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {Colors.TEXT_MUTED};
}}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    height: 0;
    background: transparent;
}}
QMenu {{
    background: {Colors.SURFACE};
    border: 1px solid {Colors.BORDER_STRONG};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 22px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {Colors.ACCENT_DIM};
}}
QMenu::separator {{
    height: 1px;
    background: {Colors.BORDER};
    margin: 6px 8px;
}}
QMessageBox QPushButton {{
    min-width: 90px;
}}
QLabel#dialogTitle {{
    font-size: 13pt;
    font-weight: 700;
    color: {Colors.TEXT};
    padding-bottom: 2px;
}}
QPushButton#optionButton {{
    text-align: left;
    padding: 12px 18px;
    font-weight: 400;
}}
"""


def apply_theme(app: QApplication) -> None:
    """Aplica o tema escuro ao aplicativo inteiro."""
    app.setStyle("Fusion")  # base neutra e igual em qualquer sistema
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(BASE_FONT_SIZE)
    app.setFont(font)
    app.setPalette(_palette())
    app.setStyleSheet(STYLESHEET)


def media_icon(kind: str, size: int = 64, fill: str = "#FFFFFF") -> QIcon:
    """Ícones de play/pause desenhados na cor pedida (os do sistema são
    escuros e somem sobre o botão violeta)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(fill))
    if kind == "play":
        s = size
        painter.drawPolygon(QPolygonF([QPointF(s * 0.30, s * 0.20), QPointF(s * 0.30, s * 0.80), QPointF(s * 0.80, s * 0.50)]))
    else:  # pause
        bar_w, bar_h, top = size * 0.18, size * 0.56, size * 0.22
        painter.drawRoundedRect(size * 0.27, top, bar_w, bar_h, 3, 3)
        painter.drawRoundedRect(size * 0.55, top, bar_w, bar_h, 3, 3)
    painter.end()
    return QIcon(pixmap)
