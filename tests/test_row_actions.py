"""Ícones à direita de cada música (no lugar do menu do botão direito)."""

import pytest
from conftest import add_song, add_stems
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolTip

from karaoke.views.icons import ICON_NAMES, icon_pixmap

LRC = "[00:05.00]um\n[00:10.00]dois\n[00:15.00]três\n"
SIGNALS = {
    "play": "play_requested",
    "search": "manual_lyrics_requested",
    "delete": "delete_requested",
}


@pytest.fixture
def lists(qapp, dirs):
    from test_controller import make

    music, separated = dirs
    add_song(music, "fila.m4a")
    for name in ("a", "b"):
        add_song(music, f"{name}.m4a")
        add_stems(separated, name)
    letras = music.parent / "letras"
    letras.mkdir()
    (letras / "a.lrc").write_text(LRC)  # "a" tem letra sincronizada; "b" não tem letra
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    view.resize(1000, 700)
    view.show()
    QTest.qWaitForWindowExposed(view)
    # só a janela: o controlador não recebe os pedidos (sem diálogos nem player)
    got = []
    for key, name in SIGNALS.items():
        signal = getattr(view, name)
        signal.disconnect()
        signal.connect(lambda arg, key=key: got.append((key, arg)))
    yield view, ctrl, music, letras, got
    view.close()


def _row(ctrl, music, name):
    return ctrl.processed.index_of(music / f"{name}.m4a")


def _click(lv, index, key, double=False):
    point = lv.action_rect(index, key).center()
    assert not lv.action_rect(index, key).isNull()
    if double:
        QTest.mouseDClick(lv.viewport(), Qt.MouseButton.LeftButton, pos=point)
    else:
        QTest.mouseClick(lv.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QApplication.processEvents()


def test_processed_songs_have_three_icons_in_order(lists):
    view, ctrl, music, _, _ = lists
    lv = view.processed_panel.view
    keys = [a.key for a in lv.actions_for(_row(ctrl, music, "a"))]
    assert keys == ["play", "search", "delete"]
    boxes = [lv.action_rect(_row(ctrl, music, "a"), k) for k in keys]
    assert all(left.right() < right.left() for left, right in zip(boxes, boxes[1:]))
    assert boxes[-1].right() <= lv.viewport().width()  # cabem na lista, à direita
    pending = view.pending_panel.view
    assert [a.key for a in pending.actions_for(pending.model().index(0, 0))] == ["delete"]


@pytest.mark.parametrize("key", ["play", "search", "delete"])
def test_clicking_icon_emits_request(lists, key):
    view, ctrl, music, _, got = lists
    path = str(music / "a.m4a")
    _click(view.processed_panel.view, _row(ctrl, music, "a"), key)
    assert got == [(key, [path] if key == "delete" else path)]
    assert view.processed_panel.view.currentIndex() == _row(ctrl, music, "a")


def test_disabled_icons_do_nothing(lists, monkeypatch):
    from karaoke.views.song_delegate import RowAction

    view, ctrl, music, _, got = lists
    lv = view.processed_panel.view
    monkeypatch.setattr(lv.itemDelegate(), "actions",
                        lambda song: [RowAction("search", "Indisponível", enabled=False)])
    _click(lv, _row(ctrl, music, "b"), "search")
    assert got == []


def test_double_click_on_icon_does_not_open_player(lists):
    view, ctrl, music, _, got = lists
    lv = view.processed_panel.view
    _click(lv, _row(ctrl, music, "a"), "search")
    _click(lv, _row(ctrl, music, "a"), "search", double=True)
    assert [k for k, _ in got] == ["search"]  # o duplo clique no ícone não abre o player
    got.clear()
    center = lv.visualRect(_row(ctrl, music, "a")).center() - QPoint(200, 0)
    QTest.mouseClick(lv.viewport(), Qt.MouseButton.LeftButton, pos=center)
    QTest.mouseDClick(lv.viewport(), Qt.MouseButton.LeftButton, pos=center)
    assert set(got) == {("play", str(music / "a.m4a"))}  # fora dos ícones, continua abrindo


def test_press_on_icon_and_release_elsewhere_cancels(lists):
    view, ctrl, music, _, got = lists
    lv = view.processed_panel.view
    index = _row(ctrl, music, "a")
    QTest.mousePress(lv.viewport(), Qt.MouseButton.LeftButton, pos=lv.action_rect(index, "delete").center())
    assert lv.itemDelegate().pressed_action == (index.row(), "delete")
    QTest.mouseRelease(lv.viewport(), Qt.MouseButton.LeftButton, pos=lv.action_rect(index, "play").center())
    assert got == [] and lv.itemDelegate().pressed_action is None


def test_pending_delete_icon(lists):
    view, ctrl, music, _, got = lists
    pending = view.pending_panel.view
    _click(pending, pending.model().index(0, 0), "delete")
    assert got == [("delete", [str(music / "fila.m4a")])]


def test_delete_icon_keeps_multiple_selection_and_deletes_only_its_row(lists):
    view, ctrl, music, _, got = lists
    lv = view.processed_panel.view
    lv.selectAll()
    _click(lv, _row(ctrl, music, "b"), "delete")
    assert got == [("delete", [str(music / "b.m4a")])]
    assert len(lv.selectionModel().selectedRows()) == 2


def test_hover_highlights_icon_and_shows_description(lists, monkeypatch):
    view, ctrl, music, _, _ = lists
    lv = view.processed_panel.view
    index = _row(ctrl, music, "a")
    point = lv.action_rect(index, "search").center()
    move = QMouseEvent(QEvent.Type.MouseMove, QPointF(point), QPointF(lv.viewport().mapToGlobal(point)),
                       Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(lv.viewport(), move)
    assert lv.itemDelegate().hovered_action == (index.row(), "search")
    assert lv.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor

    shown = []
    monkeypatch.setattr(QToolTip, "showText", lambda pos, text, *args: shown.append(text))
    from PySide6.QtGui import QHelpEvent

    for key, text in [("play", "Abrir no player (Enter)"), ("delete", "Excluir (Delete)"),
                      ("search", "Buscar letra manualmente (Ctrl+B)")]:
        p = lv.action_rect(index, key).center()
        QApplication.sendEvent(lv.viewport(), QHelpEvent(QEvent.Type.ToolTip, p, lv.viewport().mapToGlobal(p)))
        assert shown[-1] == text
    title = lv.visualRect(index).topLeft() + QPoint(40, 20)
    QApplication.sendEvent(lv.viewport(), QHelpEvent(QEvent.Type.ToolTip, title, lv.viewport().mapToGlobal(title)))
    assert shown[-1].startswith("a.m4a")  # sobre o nome, continua a descrição da música

    leave = QEvent(QEvent.Type.Leave)
    QApplication.sendEvent(lv, leave)
    assert lv.itemDelegate().hovered_action is None


def test_no_context_menu_on_right_click(lists):
    view, *_ = lists
    lv = view.processed_panel.view
    assert lv.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu
    assert not hasattr(view, "build_processed_menu")


@pytest.mark.parametrize("name", ICON_NAMES)
def test_icons_render(qapp, name):
    pixmap = icon_pixmap(name, "#E7E9EE", 18, 2.0)
    image = pixmap.toImage()
    assert pixmap.deviceIndependentSize().width() == 18
    assert any(image.pixelColor(x, y).alpha() for x in range(image.width()) for y in range(image.height()))
