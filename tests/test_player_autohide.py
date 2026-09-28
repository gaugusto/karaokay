"""Controles do player somem após um tempo parado e voltam com qualquer interação."""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from karaoke.views import MainWindow, PlayerWindow
from karaoke.views.player_window import CONTROLS_FADE_MS, CONTROLS_IDLE_MS

IDLE, FADE = 60, 40  # ms, encurtados para o teste


@pytest.fixture
def player(qapp):
    main = MainWindow()
    main.resize(1000, 760)
    view = PlayerWindow()
    view.controls_idle_ms = IDLE
    view._fade.setDuration(FADE)
    main.show_page(view, "Música")
    main.show()
    QTest.qWaitForWindowExposed(main)
    QApplication.processEvents()
    yield view, main
    view.close_without_asking()
    main.close_guard = None
    main.close()


def move_mouse(widget, pos=None):
    """Movimento real do mouse (vai para a janela, como no sistema)."""
    pos = pos or QPoint(widget.width() // 2, widget.height() // 2)
    move_mouse.n = getattr(move_mouse, "n", 0) + 1
    pos = pos + QPoint(move_mouse.n % 7, 0)  # posição nova a cada chamada
    global_pos = widget.mapToGlobal(pos)
    window = widget.window().windowHandle()
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(window.mapFromGlobal(global_pos)), QPointF(global_pos),
                        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, event)


def wait_for(condition, timeout=3000):
    for _ in range(timeout // 10):
        if condition():
            return True
        QTest.qWait(10)
    return condition()


def wait_hidden(view):
    assert wait_for(lambda: not view.controls_visible and view.controls_opacity == 0.0)


def test_defaults():
    assert CONTROLS_IDLE_MS == 3000 and CONTROLS_FADE_MS == 500


def test_controls_fade_out_after_idle(player):
    view, _ = player
    view.controls_idle_ms = 5000
    view.show_controls()
    assert wait_for(lambda: view.controls_opacity == 1.0)  # abre com os controles à vista
    view._fade.setDuration(400)
    view.controls_idle_ms = IDLE
    view.show_controls()  # recomeça a contagem
    assert wait_for(lambda: not view.controls_visible)
    QTest.qWait(50)
    assert 0.0 < view.controls_opacity < 1.0  # animando
    wait_hidden(view)
    for widget in (view.close_button, view.play_button, view.font_larger_button):
        assert widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) or \
            widget.parentWidget().testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert view.cursor().shape() == Qt.CursorShape.BlankCursor
    assert view.title_label.isVisible()  # o título continua
    assert view.controls_card.isVisible()  # o espaço fica reservado: a letra não pula


@pytest.mark.parametrize("how", ["mouse", "key", "wheel", "click"])
def test_interaction_brings_controls_back(player, how):
    view, main = player
    wait_hidden(view)
    assert view.controls_opacity == 0.0
    target = view.lyrics_view.viewport()
    view.controls_idle_ms = 2000  # tempo de sobra para ver a volta completa
    if how == "mouse":
        move_mouse(target)
    elif how == "key":
        QTest.keyClick(view, Qt.Key.Key_Shift)
    elif how == "wheel":
        from PySide6.QtGui import QWheelEvent

        QApplication.sendEvent(target, QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                                                   Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                                   Qt.ScrollPhase.NoScrollPhase, False))
    else:
        QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    assert view.controls_visible and view.cursor().shape() != Qt.CursorShape.BlankCursor
    assert wait_for(lambda: view.controls_opacity == 1.0)
    assert not view.close_button.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    # e somem de novo depois de mais um tempo parado
    view.controls_idle_ms = IDLE
    view._idle_timer.start(IDLE)
    wait_hidden(view)
    assert not view.controls_visible


def test_repeated_interaction_keeps_controls(player):
    view, _ = player
    view.controls_idle_ms = 200
    view.show_controls()
    wait_for(lambda: view.controls_opacity == 1.0)
    for _ in range(5):
        QTest.qWait(80)
        move_mouse(view.lyrics_view.viewport())
    assert view.controls_visible and view.controls_opacity == 1.0


def test_same_mouse_position_is_not_interaction(player):
    view, _ = player
    wait_hidden(view)
    window = view.window().windowHandle()
    pos = QPointF(view.window().width() / 2, view.window().height() / 2)  # sobre a letra
    event = QMouseEvent(QEvent.Type.MouseMove, pos, window.mapToGlobal(pos), Qt.MouseButton.NoButton,
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, event)
    wait_hidden(view)  # voltou a aparecer e sumiu de novo
    view._last_mouse_pos = window.mapToGlobal(pos).toPoint()
    QApplication.sendEvent(window, QMouseEvent(event))
    assert not view.controls_visible  # mesma posição: o sistema repetiu, ninguém mexeu


def test_sync_mode_keeps_controls_visible(player):
    view, _ = player
    wait_hidden(view)
    view.set_sync_mode(True, 0)
    assert view.controls_visible
    QTest.qWait(IDLE * 3)
    assert view.controls_visible
    view.set_sync_mode(False)
    wait_hidden(view)
    assert not view.controls_visible


def test_controls_stay_while_mouse_is_over_them(player, monkeypatch):
    view, _ = player
    from PySide6.QtWidgets import QWidget

    monkeypatch.setattr(QWidget, "underMouse", lambda self: self is view.controls_card)
    view.show_controls()
    assert wait_for(lambda: view.controls_opacity == 1.0)
    QTest.qWait(IDLE * 3)
    assert view.controls_visible


def click_window(window, pos):
    """Clique sem esperas no meio (o QTest.mouseClick deixa o tempo correr)."""
    local, global_pos = QPointF(pos), QPointF(window.mapToGlobal(pos))
    for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                          (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(window, QMouseEvent(kind, local, global_pos, Qt.MouseButton.LeftButton,
                                                   buttons, Qt.KeyboardModifier.NoModifier))


def test_click_that_reveals_does_not_hit_invisible_button(player):
    view, _ = player
    wait_hidden(view)
    view._fade.setDuration(400)
    view.controls_idle_ms = 3000
    closed = []
    view.close_button.clicked.connect(lambda: closed.append(True))
    window = view.window().windowHandle()
    center = view.close_button.mapTo(view.window(), view.close_button.rect().center())
    click_window(window, center)
    QApplication.processEvents()
    assert closed == [] and view.controls_visible
    assert wait_for(lambda: view.controls_opacity >= 0.5)
    click_window(window, center)  # já visível: agora aciona
    assert closed == [True]


def test_hidden_player_stops_watching(player):
    view, main = player
    main.show_library(view)
    QApplication.processEvents()
    assert not view._watching and not view._idle_timer.isActive()
