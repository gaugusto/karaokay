"""Ícones de linha (traço fino, 24×24) desenhados na cor pedida.

São SVGs pequenos escritos aqui mesmo: não dependem do tema de ícones do
sistema (que pode faltar ou ser escuro demais para o fundo do app).
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    # Abrir no player
    "play": '<path d="M8 5.5v13l10.5-6.5z" fill="{c}"/>',
    # Sincronizar automaticamente (setas girando)
    "sync": '<path d="M20 12a8 8 0 0 1-14.3 4.9"/><path d="M4 12a8 8 0 0 1 14.3-4.9"/>'
            '<path d="M18.6 3v4.6H14"/><path d="M5.4 21v-4.6H10"/>',
    # Restaurar a letra original (desfazer)
    "restore": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    # Buscar letra manualmente (lupa)
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.5-4.5"/>',
    # Excluir (lixeira)
    "delete": '<path d="M4 7h16"/><path d="M10 11v6"/><path d="M14 11v6"/>'
              '<path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/>'
              '<path d="M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7"/>',
}

ICON_NAMES = tuple(_PATHS)


def icon_svg(name: str, color: str) -> str:
    body = _PATHS[name].format(c=color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )


@lru_cache(maxsize=128)
def icon_pixmap(name: str, color: str, size: int, ratio: float = 1.0) -> QPixmap:
    """Ícone ``name`` em ``color`` (#RRGGBB), com ``size`` px lógicos."""
    pixels = max(1, round(size * ratio))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(icon_svg(name, color).encode()))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap
