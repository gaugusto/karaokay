"""O player ocupa a janela principal; ao fechar (✕, Esc, Ctrl+W) as listas voltam."""

import pytest
from conftest import add_song, add_stems
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from karaoke.controllers import PlayerController
from karaoke.services import PlayerState
from test_player import LRC, FakePlayer, answers  # noqa: F401 (fixture)


@pytest.fixture
def app(qapp, dirs, monkeypatch):
    from test_controller import make

    music, separated = dirs
    for name in ("a", "b"):
        add_song(music, f"{name}.m4a")
        add_stems(separated, name)
        (music.parent / "letras").mkdir(exist_ok=True)
        (music.parent / "letras" / f"{name}.lrc").write_text(LRC)
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    view.show()
    player = FakePlayer()
    monkeypatch.setattr(
        "karaoke.controllers.app_controller.PlayerController",
        lambda song, view=None, parent=None: PlayerController(song, view, player, parent),
    )
    yield view, ctrl, player, music
    view.close_guard = None
    view.close()


def _open(ctrl, music, name="b"):
    ctrl.open_player(str(music / f"{name}.m4a"))
    QApplication.processEvents()
    return ctrl.player.view


def test_player_takes_over_main_window(app):
    view, ctrl, _, music = app
    player_view = _open(ctrl, music)
    assert view.showing_page
    assert view.stack.currentWidget() is player_view
    assert player_view.embedded and player_view.window() is view
    assert "b" in view.windowTitle()
    assert not view.library_page.isVisible()


@pytest.mark.parametrize("how", ["button", "esc", "ctrl_w"])
def test_closing_player_returns_to_lists(app, how):
    view, ctrl, player, music = app
    player_view = _open(ctrl, music, "b")
    if how == "button":
        player_view.close_button.click()
    elif how == "esc":
        QTest.keyClick(player_view, Qt.Key.Key_Escape)
    else:
        QTest.keyClick(player_view, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()

    assert ctrl.player is None and ("stop",) in player.calls
    assert not view.showing_page
    assert view.stack.count() == 1  # só a biblioteca
    assert view.windowTitle() == "Karaokê"
    # a música que estava tocando fica selecionada na lista de processadas
    current = view.processed_panel.view.currentIndex()
    assert current.isValid() and current.row() == ctrl.processed.index_of(music / "b.m4a").row()


def test_closing_while_playing_asks(app, answers):  # noqa: F811
    view, ctrl, player, music = app
    player_view = _open(ctrl, music)
    player.state = PlayerState.PLAYING
    player.state_changed.emit(PlayerState.PLAYING)

    answers["answer"] = False
    player_view.close_button.click()
    assert answers["asked"] == ["Fechar o player"]
    assert view.showing_page and ctrl.player is not None

    answers["answer"] = True
    player_view.close_button.click()
    QApplication.processEvents()
    assert not view.showing_page and ctrl.player is None


def test_fullscreen_acts_on_main_window_and_is_undone_on_close(app):
    view, ctrl, _, music = app
    player_view = _open(ctrl, music)
    player_view.set_fullscreen(True)
    assert view.windowState() & Qt.WindowState.WindowFullScreen
    assert player_view.is_fullscreen

    player_view._on_escape()  # 1º Esc: só sai da tela cheia
    assert not (view.windowState() & Qt.WindowState.WindowFullScreen)
    assert view.showing_page

    player_view.set_fullscreen(True)
    player_view.close_button.click()  # fechar na tela cheia devolve a janela ao normal
    QApplication.processEvents()
    assert not (view.windowState() & Qt.WindowState.WindowFullScreen)
    assert not view.showing_page


def test_opening_another_song_replaces_player(app):
    view, ctrl, _, music = app
    first = _open(ctrl, music, "a")
    second = _open(ctrl, music, "b")
    assert first is not second
    assert view.stack.currentWidget() is second
    assert view.stack.count() == 2  # biblioteca + um player


def test_ctrl_l_does_nothing_while_player_is_shown(app):
    view, ctrl, _, music = app
    _open(ctrl, music)
    view.focus_url_bar()
    assert not view.url_bar.hasFocus()
    assert view.showing_page
