"""Navegação por teclado: janela principal, busca de letra e player."""

import pytest
from conftest import add_song, add_stems
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from karaoke.models import parse_lrc

LRC = "[00:05.00]a\n[00:10.00]b\n[00:15.00]c\n"


def activate(window):
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)


def focused():
    return QApplication.focusWidget()


def tab(times=1, back=False):
    for _ in range(times):
        QTest.keyClick(focused(), Qt.Key.Key_Backtab if back else Qt.Key.Key_Tab)


# ------------------------------------------------------------ janela principal
@pytest.fixture
def main(qapp, dirs):
    from test_controller import make

    music, separated = dirs
    add_song(music, "fila.m4a")
    for name in ("a", "b"):
        add_song(music, f"{name}.m4a")
        add_stems(separated, name)
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    activate(view)
    view.url_bar.setFocus()
    return view, ctrl, music


def test_tab_cycles_url_bar_and_lists(main):
    view, ctrl, music = main
    tab()
    assert focused() is view.pending_panel.view
    assert view.pending_panel.view.currentIndex().row() == 0  # já marca a 1ª música
    tab()
    assert focused() is view.processed_panel.view
    tab(back=True)
    assert focused() is view.pending_panel.view
    QTest.keyClick(focused(), Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
    assert focused() is view.url_bar


def test_arrows_and_enter_open_processed_song(main):
    view, ctrl, music = main
    played = []
    view.play_requested.connect(played.append)
    lv = view.processed_panel.view
    lv.setFocus()
    QTest.keyClick(lv, Qt.Key.Key_Down)
    assert lv.currentIndex().data() == "b"
    QTest.keyClick(lv, Qt.Key.Key_Return)
    assert played == [str(music / "b.m4a")]


def test_icon_shortcuts_act_on_current_song(main):
    view, ctrl, music = main
    got = []
    for signal in (view.auto_sync_requested, view.restore_lyrics_requested, view.manual_lyrics_requested):
        signal.disconnect()
    view.auto_sync_requested.connect(lambda p: got.append(("sync", p)))
    view.restore_lyrics_requested.connect(lambda p: got.append(("restore", p)))
    view.manual_lyrics_requested.connect(lambda p: got.append(("search", p)))
    lv = view.processed_panel.view
    lv.setFocus()
    QTest.keyClick(lv, Qt.Key.Key_Down)  # "b"
    QTest.keyClick(lv, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert got == [("search", str(music / "b.m4a"))]
    # sem letra sincronizada nem cópia: Ctrl+S e Ctrl+R não fazem nada
    QTest.keyClick(lv, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(lv, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    assert len(got) == 1


# ------------------------------------------------------------------ player
@pytest.fixture
def player(qapp):
    from test_player import FakePlayer

    from karaoke.controllers import PlayerController
    from karaoke.views import PlayerWindow

    class Song:  # só o que o controlador usa
        title = "Música"
        lyrics_path = None
        vocals_path = instrumental_path = None

    view, fake = PlayerWindow(), FakePlayer()
    view.set_lyrics(parse_lrc(LRC))
    view.set_duration(200)
    view.set_loading(False)
    ctrl = PlayerController.__new__(PlayerController)  # sem carregar áudio
    activate(view)
    return view, fake


def _record(view):
    calls = []
    view.toggle_requested.connect(lambda: calls.append("toggle"))
    view.seek_requested.connect(lambda s: calls.append(("seek", round(s, 1))))
    view.seek_relative_requested.connect(lambda d: calls.append(("rel", d)))
    return calls


def test_player_starts_on_play_and_tab_order(player):
    view, _ = player
    assert focused() is view.play_button
    expected = [
        view.position_slider, view.sync_button, view.vocal_volume.slider,
        view.instrumental_volume.slider, view.fullscreen_button, view.effect_button,
        view.font_smaller_button, view.font_larger_button,
    ]
    for widget in expected:
        tab()
        assert focused() is widget, widget


def test_space_and_arrows_from_buttons_and_sliders(player):
    view, _ = player
    calls = _record(view)
    QTest.keyClick(view.play_button, Qt.Key.Key_Space)   # botão play: clica = toggle
    QTest.keyClick(view.play_button, Qt.Key.Key_Right)   # setas num botão: +5 s
    assert calls == ["toggle", ("rel", 5)]

    calls.clear()
    view.vocal_volume.slider.setFocus()
    QTest.keyClick(view.vocal_volume.slider, Qt.Key.Key_Space)  # espaço num slider: toggle
    QTest.keyClick(view.vocal_volume.slider, Qt.Key.Key_Right)  # setas: mexem no volume
    assert calls == ["toggle"]
    assert view.vocal_volume.slider.value() == 35


def test_position_slider_keys_seek(player):
    view, _ = player
    calls = _record(view)
    view.set_position(50)
    view.position_slider.setFocus()
    QTest.keyClick(view.position_slider, Qt.Key.Key_Right)
    QTest.qWait(20)
    QTest.keyClick(view.position_slider, Qt.Key.Key_PageDown)  # PageDown = -30 s no slider horizontal
    QTest.qWait(20)
    assert calls == [("seek", 55.0), ("seek", 25.0)]


def test_enter_activates_focused_button(player):
    view, _ = player
    size = view.font_size
    view.font_larger_button.setFocus()
    QTest.keyClick(view.font_larger_button, Qt.Key.Key_Return)
    QTest.qWait(250)  # animateClick
    assert view.font_size == size + 2


def test_m_marks_first_verse_in_sync_mode(player):
    view, _ = player
    marked = []
    view.sync_line_clicked.connect(marked.append)
    QTest.keyClick(view.play_button, Qt.Key.Key_M)
    assert marked == []  # fora da sincronização, M não faz nada
    view.set_sync_mode(True, 0)
    QTest.keyClick(view.play_button, Qt.Key.Key_M)
    assert marked == [0]
    assert "tecle M" in view.lyrics_note.text()


# --------------------------------------------------------- busca de letra
def test_search_dialog_keyboard(qapp):
    from karaoke.models import LyricsState
    from karaoke.views import LyricsSearchPage

    dialog = LyricsSearchPage("Música")
    searches, accepted = [], []
    dialog.search_requested.connect(lambda a, t: searches.append((a, t)))
    dialog.accepted.connect(lambda: accepted.append(True))
    activate(dialog)
    dialog.track_edit.setFocus()
    dialog.track_edit.setText("Lugar ao Sol")
    record = {"trackName": "Lugar ao Sol", "artistName": "A", "duration": 200,
              "syncedLyrics": LRC, "plainLyrics": "a"}
    dialog.set_results([record], [LyricsState.SYNCED])  # já há um resultado selecionável

    QTest.keyClick(dialog.track_edit, Qt.Key.Key_Return)
    assert searches == [("", "Lugar ao Sol")] and accepted == []  # Enter no campo só busca
    dialog.set_results([record], [LyricsState.SYNCED])

    QTest.keyClick(dialog.track_edit, Qt.Key.Key_Down)
    assert focused() is dialog.table
    QTest.keyClick(dialog.table, Qt.Key.Key_Return)
    assert accepted == [True]  # Enter no resultado usa a letra


def test_windows_build_without_tab_order_warnings(qapp):
    """setTabOrder só vale para widgets já na mesma janela; senão o Qt avisa
    "'first' and 'second' must be in the same window" e ignora a ordem."""
    from PySide6.QtCore import qInstallMessageHandler

    from karaoke.views import LyricsSearchPage, MainWindow, PlayerWindow

    warnings = []
    previous = qInstallMessageHandler(lambda mode, ctx, msg: warnings.append(msg))
    try:
        MainWindow()
        PlayerWindow()
        LyricsSearchPage("Música")
    finally:
        qInstallMessageHandler(previous)
    assert [w for w in warnings if "setTabOrder" in w] == []


def test_search_dialog_tab_order(qapp):
    from karaoke.views import LyricsSearchPage

    dialog = LyricsSearchPage("Música")
    activate(dialog)
    dialog.artist_edit.setFocus()
    for widget in [dialog.track_edit, dialog.search_button, dialog.table, dialog.preview]:
        tab()
        assert focused() is widget, widget
