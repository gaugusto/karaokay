"""Fundo animado do player: manchas de luz suaves que reagem à música.

Pensado para não atrapalhar a leitura: cores escuras e pouco opacas, e um
véu escuro na faixa do meio, onde fica o verso atual.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from karaoke.views.theme import Colors

FRAME_MS = 33  # ~30 quadros por segundo


@dataclass(frozen=True)
class _Blob:
    color: str
    radius: float  # fração do maior lado da janela
    speed: float   # voltas por minuto, aproximadamente
    phase: float
    alpha: int     # opacidade no centro da mancha (0–255), em repouso


# Opacidades escolhidas medindo o contraste da letra no pior momento da
# animação (ver tests/test_background.py).
BLOBS = (
    _Blob("#6D28D9", 0.55, 1.6, 0.0, 56),  # violeta
    _Blob("#1D4ED8", 0.50, 1.2, 2.1, 48),  # índigo
    _Blob("#0F766E", 0.45, 1.9, 4.2, 44),  # azul-petróleo
    _Blob("#9D174D", 0.40, 1.4, 5.3, 32),  # magenta escuro
)

# Véu escuro na faixa central (onde fica o verso atual), em fração da altura
VEIL_ALPHA = 150


class AnimatedBackground(QWidget):
    """Widget que fica atrás do conteúdo do player e desenha o fundo."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._time = 0.0
        self._level = 0.0   # intensidade atual (suavizada)
        self._target = 0.0  # intensidade pedida pela música (0–1)
        self._enabled = True
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._advance)

    # A animação só roda com o fundo visível (janela fechada/minimizada: parada)
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._enabled:
            self._timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    @property
    def animating(self) -> bool:
        return self._timer.isActive()

    # ------------------------------------------------------------ controle
    @property
    def effect_enabled(self) -> bool:
        return self._enabled

    def set_effect_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled and self.isVisible():
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def set_level(self, level: float) -> None:
        """Intensidade do som (0–1); o brilho acompanha com suavidade."""
        self._target = max(0.0, min(1.0, level))

    def advance(self, seconds: float) -> None:
        """Avança a animação (usado pelo timer e pelos testes)."""
        self._time += seconds
        self._level += (self._target - self._level) * 0.12
        self.update()

    def _advance(self) -> None:
        self.advance(FRAME_MS / 1000)

    # ------------------------------------------------------------- desenho
    def blob_centers(self) -> list[QPointF]:
        w, h = self.width(), self.height()
        centers = []
        for blob in BLOBS:
            angle = self._time * blob.speed * 2 * math.pi / 60 + blob.phase
            centers.append(
                QPointF(
                    w * (0.5 + 0.42 * math.sin(angle)),
                    h * (0.5 + 0.38 * math.cos(angle * 0.8 + blob.phase * 1.3)),
                )
            )
        return centers

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = QRectF(self.rect())
        painter.fillRect(rect, QColor(Colors.BACKGROUND))
        if not self._enabled:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = max(rect.width(), rect.height())
        boost = 1.0 + 0.6 * self._level
        for blob, center in zip(BLOBS, self.blob_centers()):
            radius = size * blob.radius * (1.0 + 0.12 * self._level)
            gradient = QRadialGradient(center, radius)
            core = QColor(blob.color)
            core.setAlpha(min(255, int(blob.alpha * boost)))
            edge = QColor(blob.color)
            edge.setAlpha(0)
            gradient.setColorAt(0.0, core)
            gradient.setColorAt(1.0, edge)
            painter.fillRect(rect, gradient)

        # Véu escuro no meio, para o verso atual ficar sempre legível
        veil = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        clear = QColor(Colors.BACKGROUND)
        clear.setAlpha(0)
        dark = QColor(Colors.BACKGROUND)
        dark.setAlpha(VEIL_ALPHA)
        veil.setColorAt(0.0, clear)
        veil.setColorAt(0.30, dark)
        veil.setColorAt(0.70, dark)
        veil.setColorAt(1.0, clear)
        painter.fillRect(rect, veil)
