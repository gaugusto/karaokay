"""Divisória arrastável com alça visível (no tema escuro ela sumia)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSplitter, QSplitterHandle

from karaoke.views.theme import Colors, color

HANDLE_SIZE = 16     # px: área de arrastar
GRIP_LENGTH = 56     # px: pegador no meio
GRIP_THICKNESS = 5   # px


class _GripHandle(QSplitterHandle):
    """Linha fina de ponta a ponta + pegador arredondado no meio.
    Fica violeta com o mouse em cima ou arrastando."""

    def __init__(self, orientation, parent) -> None:
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._pressed = False
        self.setToolTip("Arraste para mudar o tamanho das listas")

    def mousePressEvent(self, event) -> None:
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    @property
    def highlighted(self) -> bool:
        return self._pressed or self.underMouse()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        vertical = self.orientation() == Qt.Orientation.Vertical  # divisória horizontal
        active = self.highlighted
        line_color = color(Colors.ACCENT if active else Colors.BORDER_STRONG, 255 if active else 200)
        grip_color = color(Colors.ACCENT_HOVER if active else Colors.TEXT_MUTED)
        painter.setPen(Qt.PenStyle.NoPen)
        if vertical:
            cy = rect.center().y()
            painter.setBrush(line_color)
            painter.drawRect(QRectF(rect.left() + 4, cy - 0.5, rect.width() - 8, 1))
            grip = QRectF(rect.center().x() - GRIP_LENGTH / 2, cy - GRIP_THICKNESS / 2, GRIP_LENGTH, GRIP_THICKNESS)
        else:
            cx = rect.center().x()
            painter.setBrush(line_color)
            painter.drawRect(QRectF(cx - 0.5, rect.top() + 4, 1, rect.height() - 8))
            grip = QRectF(cx - GRIP_THICKNESS / 2, rect.center().y() - GRIP_LENGTH / 2, GRIP_THICKNESS, GRIP_LENGTH)
        painter.setBrush(grip_color)
        painter.drawRoundedRect(grip, GRIP_THICKNESS / 2, GRIP_THICKNESS / 2)


class GripSplitter(QSplitter):
    def __init__(self, orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self.setHandleWidth(HANDLE_SIZE)

    def createHandle(self) -> QSplitterHandle:
        return _GripHandle(self.orientation(), self)
