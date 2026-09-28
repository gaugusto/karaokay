from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from karaoke.views.splitter import GripSplitter
from karaoke.views.theme import Colors


def _make(qapp):
    splitter = GripSplitter(Qt.Orientation.Vertical)
    splitter.addWidget(QLabel("em cima"))
    splitter.addWidget(QLabel("embaixo"))
    splitter.resize(400, 400)
    splitter.show()
    return splitter


def test_handle_is_visible_and_highlights(qapp):
    splitter = _make(qapp)
    handle = splitter.handle(1)
    assert handle.height() == 16
    img = handle.grab().toImage()
    center = img.pixelColor(img.width() // 2, img.height() // 2)
    background = QColor(Colors.BACKGROUND)
    assert abs(center.lightness() - background.lightness()) > 40  # pegador aparece
    assert img.pixelColor(20, img.height() // 2).alpha() > 0      # linha de ponta a ponta

    handle._pressed = True  # arrastando: violeta
    img = handle.grab().toImage()
    grip = img.pixelColor(img.width() // 2, img.height() // 2)
    assert grip.name() == QColor(Colors.ACCENT_HOVER).name()


def test_dragging_the_handle_resizes(qapp):
    splitter = _make(qapp)
    handle = splitter.handle(1)
    before = splitter.sizes()
    center = QPoint(handle.width() // 2, handle.height() // 2)
    QTest.mousePress(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
    QTest.mouseMove(handle, center + QPoint(0, 80))
    QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center + QPoint(0, 80))
    after = splitter.sizes()
    assert after[0] > before[0] + 40 and not handle._pressed
