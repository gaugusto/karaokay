"""Temas do aplicativo: paletas, fonte e folha de estilo (QSS).

Cada tema é um ``Theme`` imutável. ``apply_theme`` troca o tema em uso a
qualquer momento: aplica paleta e QSS e avisa pelo sinal
``theme_changed.changed`` quem guardou cores (ícones, itens de lista). Quem
lê ``Colors.X`` na hora de pintar já recebe a cor do tema atual.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    BACKGROUND: str
    SURFACE: str           # cartões, campos
    SURFACE_HOVER: str
    SURFACE_RAISED: str    # botões
    SURFACE_SELECTED: str
    BORDER: str
    BORDER_STRONG: str
    TEXT: str
    TEXT_SECONDARY: str
    TEXT_MUTED: str
    LYRICS_DIM: str        # versos que não estão sendo cantados
    ACCENT: str
    ACCENT_HOVER: str
    ACCENT_PRESSED: str
    ACCENT_DIM: str
    ON_ACCENT: str         # texto/ícones sobre a cor de destaque
    SUCCESS: str
    WARNING: str
    INFO: str
    DANGER: str


@dataclass(frozen=True)
class BlobTint:
    """Cor e opacidade (0–255, em repouso) de uma mancha do fundo animado."""

    color: str
    alpha: int


@dataclass(frozen=True)
class Theme:
    name: str
    palette: Palette
    blobs: tuple[BlobTint, ...]  # uma por mancha de background.BLOBS
    veil_alpha: int              # véu na faixa central do fundo animado
    card_alpha: int              # opacidade do fundo dos cartões (QFrame#card)


DARK = Theme(
    name="violeta",
    palette=Palette(
        BACKGROUND="#111318",
        SURFACE="#1A1D24",
        SURFACE_HOVER="#212530",
        SURFACE_RAISED="#232833",
        SURFACE_SELECTED="#2A2544",
        BORDER="#2A2F3A",
        BORDER_STRONG="#363C4A",
        TEXT="#E7E9EE",
        TEXT_SECONDARY="#9AA3B2",
        TEXT_MUTED="#5F6776",
        LYRICS_DIM="#858E9E",
        ACCENT="#8B5CF6",  # violeta
        ACCENT_HOVER="#A07BFA",
        ACCENT_PRESSED="#7444E8",
        ACCENT_DIM="#3A2F63",
        ON_ACCENT="#FFFFFF",
        SUCCESS="#22C55E",
        WARNING="#F59E0B",
        INFO="#38BDF8",
        DANGER="#EF4444",
    ),
    # Opacidades escolhidas medindo o contraste da letra no pior momento da
    # animação (ver tests/test_background.py).
    blobs=(
        BlobTint("#6D28D9", 56),  # violeta
        BlobTint("#1D4ED8", 48),  # índigo
        BlobTint("#0F766E", 44),  # azul-petróleo
        BlobTint("#9D174D", 32),  # magenta escuro
    ),
    veil_alpha=150,
    card_alpha=225,
)



def _accent_variant(name: str, accent: str, hover: str, pressed: str, dim: str, selected: str) -> Theme:
    """O tema escuro com outra cor de destaque (fundo animado não muda)."""
    return replace(DARK, name=name, palette=replace(
        DARK.palette, ACCENT=accent, ACCENT_HOVER=hover, ACCENT_PRESSED=pressed,
        ACCENT_DIM=dim, SURFACE_SELECTED=selected))


ROSA = _accent_variant("rosa", "#DB2777", "#EC4899", "#BE185D", "#5A1F3D", "#3A2230")
AZUL = _accent_variant("azul", "#2563EB", "#3B82F6", "#1D4ED8", "#1E3A6B", "#1F2A44")
VERDE_AGUA = _accent_variant("verde-água", "#0D9488", "#14B8A6", "#0F766E", "#134E4A", "#1A3533")
LARANJA = _accent_variant("laranja", "#EA580C", "#F97316", "#C2410C", "#5A2A14", "#3A261E")

# Ordem em que o botão do cabeçalho percorre as cores
ACCENT_THEMES = (DARK, ROSA, AZUL, VERDE_AGUA, LARANJA)
THEMES = {t.name: t for t in ACCENT_THEMES}

_current = DARK


def current_theme() -> Theme:
    return _current


def next_theme(theme: Theme) -> Theme:
    """Tema seguinte em ``ACCENT_THEMES`` (depois do último, volta ao primeiro)."""
    try:
        i = ACCENT_THEMES.index(theme)
    except ValueError:
        return ACCENT_THEMES[0]
    return ACCENT_THEMES[(i + 1) % len(ACCENT_THEMES)]


class _CurrentColors:
    """``Colors.ACCENT`` etc.: cores do tema em uso, lidas a cada acesso."""

    def __getattr__(self, name: str) -> str:
        return getattr(_current.palette, name)


Colors = _CurrentColors()


class _ThemeNotifier(QObject):
    changed = Signal(object)  # Theme


theme_changed = _ThemeNotifier()


FONT_FAMILIES = ["Inter", "Noto Sans", "Cantarell", "Ubuntu", "DejaVu Sans"]
BASE_FONT_SIZE = 11  # pt


def color(hex_code: str, alpha: int = 255) -> QColor:
    c = QColor(hex_code)
    c.setAlpha(alpha)
    return c


def _rgba(hex_code: str, alpha: int) -> str:
    c = QColor(hex_code)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def _qpalette(p: Palette) -> QPalette:
    qp = QPalette()
    roles = {
        QPalette.ColorRole.Window: p.BACKGROUND,
        QPalette.ColorRole.WindowText: p.TEXT,
        QPalette.ColorRole.Base: p.SURFACE,
        QPalette.ColorRole.AlternateBase: p.SURFACE_HOVER,
        QPalette.ColorRole.Text: p.TEXT,
        QPalette.ColorRole.PlaceholderText: p.TEXT_MUTED,
        QPalette.ColorRole.Button: p.SURFACE_RAISED,
        QPalette.ColorRole.ButtonText: p.TEXT,
        QPalette.ColorRole.Highlight: p.ACCENT,
        QPalette.ColorRole.HighlightedText: p.ON_ACCENT,
        QPalette.ColorRole.ToolTipBase: p.SURFACE,
        QPalette.ColorRole.ToolTipText: p.TEXT,
        QPalette.ColorRole.Link: p.ACCENT_HOVER,
        QPalette.ColorRole.BrightText: p.ON_ACCENT,
    }
    for role, value in roles.items():
        qp.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        qp.setColor(QPalette.ColorGroup.Disabled, role, QColor(p.TEXT_MUTED))
    return qp


def build_stylesheet(theme: Theme) -> str:
    p = theme.palette
    return f"""
* {{
    outline: 0;
}}
QMainWindow, QDialog, QWidget#playerWindow {{
    background: {p.BACKGROUND};
}}
QToolTip {{
    background: {p.SURFACE};
    color: {p.TEXT};
    border: 1px solid {p.BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ---- títulos ---- */
QLabel#appTitle {{
    font-size: 20pt;
    font-weight: 700;
    color: {p.TEXT};
}}
QLabel#appSubtitle, QLabel#hint {{
    color: {p.TEXT_SECONDARY};
}}
QLabel#sectionHeader {{
    color: {p.TEXT_SECONDARY};
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
    background: {p.SURFACE};
    border: 1px solid {p.BORDER};
    border-radius: 10px;
    padding: 8px 12px;
    selection-background-color: {p.ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {p.ACCENT};
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
    background: {p.SURFACE_RAISED};
    border: 1px solid {p.BORDER_STRONG};
    border-radius: 10px;
    padding: 9px 18px;
    min-height: 22px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {p.SURFACE_HOVER};
    border-color: {p.TEXT_MUTED};
}}
QPushButton:pressed {{
    background: {p.SURFACE};
}}
QPushButton:disabled {{
    color: {p.TEXT_MUTED};
    border-color: {p.BORDER};
}}
QPushButton:checked {{
    background: {p.ACCENT_DIM};
    border-color: {p.ACCENT};
}}
QPushButton:default, QPushButton#primary {{
    background: {p.ACCENT};
    border: 1px solid {p.ACCENT};
    color: {p.ON_ACCENT};
}}
QPushButton:default:hover, QPushButton#primary:hover {{
    background: {p.ACCENT_HOVER};
}}
QPushButton:default:disabled, QPushButton#primary:disabled {{
    background: {p.ACCENT_DIM};
    border-color: {p.ACCENT_DIM};
    color: {p.TEXT_SECONDARY};
}}
QPushButton#fontButton {{
    padding: 0;
    font-size: 12pt;
    font-weight: 700;
    border-radius: 10px;
}}
QPushButton:focus {{
    border: 2px solid {p.ACCENT_HOVER};
}}
QPushButton:default:focus, QPushButton#primary:focus {{
    border: 2px solid {p.ON_ACCENT};
}}
QPushButton#themeButton {{
    background: {p.ACCENT};
    border: 2px solid {p.BORDER_STRONG};
    border-radius: 14px;
    min-width: 28px; max-width: 28px;
    min-height: 28px; max-height: 28px;
    padding: 0;
}}
QPushButton#themeButton:hover {{
    background: {p.ACCENT_HOVER};
    border-color: {p.TEXT_MUTED};
}}
QPushButton#playButton {{
    background: {p.ACCENT};
    border: none;
    border-radius: 28px;
    min-width: 56px; max-width: 56px;
    min-height: 56px; max-height: 56px;
    padding: 0;
}}
QPushButton#playButton:hover {{
    background: {p.ACCENT_HOVER};
}}
QPushButton#playButton:pressed {{
    background: {p.ACCENT_PRESSED};
}}
QPushButton#playButton:focus {{
    border: 3px solid {p.ON_ACCENT};
}}
QPushButton#playButton:disabled {{
    background: {p.ACCENT_DIM};
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
    background: {p.SURFACE};
    border: 1px solid {p.BORDER};
    border-radius: 10px;
    gridline-color: {p.BORDER};
    selection-background-color: {p.ACCENT_DIM};
    selection-color: {p.TEXT};
}}
QTableWidget::item {{
    padding: 6px;
}}
QTableWidget:focus {{
    border: 1px solid {p.ACCENT};
}}
QHeaderView::section {{
    background: {p.SURFACE_RAISED};
    color: {p.TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {p.BORDER};
    padding: 8px;
    font-weight: 600;
}}

/* ---- resultados do YouTube ---- */
QListWidget#results {{
    background: transparent;
    border: none;
}}
QListWidget#results::item {{
    background: {p.SURFACE};
    border: 1px solid {p.BORDER};
    border-radius: 12px;
}}
QListWidget#results::item:hover {{
    background: {p.SURFACE_HOVER};
}}
QListWidget#results::item:selected {{
    background: {p.SURFACE_SELECTED};
    border: 1px solid {p.ACCENT};
}}
QLabel#resultTitle {{
    font-size: 12pt;
    font-weight: 600;
    background: transparent;
}}
QLabel#thumbnail {{
    background: {p.SURFACE_RAISED};
    border-radius: 8px;
}}

/* ---- cartões ---- */
QFrame#card {{
    background: {_rgba(p.SURFACE, theme.card_alpha)};
    border: 1px solid {p.BORDER};
    border-radius: 16px;
}}
QFrame#card QLabel {{
    background: transparent;
}}

/* ---- sliders e progresso ---- */
QSlider::groove:horizontal {{
    height: 6px;
    background: {p.BORDER_STRONG};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {p.ACCENT};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {p.ON_ACCENT};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:focus {{
    background: {p.ACCENT_HOVER};
    border: 2px solid {p.ON_ACCENT};
}}
QSlider::handle:horizontal:hover {{
    background: {p.ACCENT_HOVER};
}}
QSlider::sub-page:horizontal:disabled {{
    background: {p.TEXT_MUTED};
}}
QProgressBar {{
    background: {p.BORDER_STRONG};
    border: none;
    border-radius: 4px;
    max-height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {p.ACCENT};
    border-radius: 4px;
}}

/* ---- barra de status, divisórias, rolagem, menus ---- */
QStatusBar {{
    background: {p.SURFACE};
    color: {p.TEXT_SECONDARY};
    border-top: 1px solid {p.BORDER};
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
    background: {p.BORDER_STRONG};
    border-radius: 4px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.TEXT_MUTED};
}}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    height: 0;
    background: transparent;
}}
QMenu {{
    background: {p.SURFACE};
    border: 1px solid {p.BORDER_STRONG};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 22px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {p.ACCENT_DIM};
}}
QMenu::separator {{
    height: 1px;
    background: {p.BORDER};
    margin: 6px 8px;
}}
QMessageBox QPushButton {{
    min-width: 90px;
}}
QLabel#dialogTitle {{
    font-size: 13pt;
    font-weight: 700;
    color: {p.TEXT};
    padding-bottom: 2px;
}}
QPushButton#optionButton {{
    text-align: left;
    padding: 12px 18px;
    font-weight: 400;
}}
"""


def apply_theme(app: QApplication, theme: Theme = DARK) -> None:
    """Aplica ``theme`` ao aplicativo inteiro (pode ser chamada de novo para
    trocar de tema com as janelas abertas)."""
    global _current
    app.setStyle("Fusion")  # base neutra e igual em qualquer sistema
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(BASE_FONT_SIZE)
    app.setFont(font)
    _current = theme
    app.setPalette(_qpalette(theme.palette))
    app.setStyleSheet(build_stylesheet(theme))
    theme_changed.changed.emit(theme)


def media_icon(kind: str, size: int = 64, fill: str | None = None) -> QIcon:
    """Ícones de play/pause desenhados na cor pedida (os do sistema são
    escuros e somem sobre o botão de destaque). Sem ``fill``: ``ON_ACCENT``."""
    fill = fill or Colors.ON_ACCENT
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
