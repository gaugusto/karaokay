"""Filtro da lista "Processadas"."""

import pytest
from conftest import add_song, add_stems
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from karaoke.models import MusicLibraryModel
from karaoke.models.song_lists import normalize, processed_songs

NAMES = ["Evidências (Remastered 2020)", "Los Hermanos - Anna Júlia", "Lugar Ao Sol", "Night Moves (Remastered 2011)"]


@pytest.fixture
def main(qapp, dirs):
    from test_controller import make

    music, separated = dirs
    for name in NAMES:
        add_song(music, f"{name}.m4a")
        add_stems(separated, name)
    add_song(music, "Na fila.m4a")  # "A processar": o filtro não mexe nela
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    view.show()
    view.activateWindow()
    assert QTest.qWaitForWindowActive(view)
    yield view, ctrl, music
    view.close()


def titles(model):
    return [model.song_at(row).title for row in range(model.rowCount())]


def test_normalize_ignores_case_and_accents():
    assert normalize("Evidências ÁGUA") == "evidencias agua"


def test_model_filters_by_all_words_any_order(qapp, dirs):
    music, separated = dirs
    for name in NAMES:
        add_song(music, f"{name}.m4a")
        add_stems(separated, name)
    library = MusicLibraryModel(music, separated)
    library.scan()
    model = processed_songs(library)
    model.set_text_filter("  REMASTERED  ")
    assert titles(model) == ["Evidências (Remastered 2020)", "Night Moves (Remastered 2011)"]
    model.set_text_filter("julia hermanos")  # sem acento, fora de ordem
    assert titles(model) == ["Los Hermanos - Anna Júlia"]
    assert model.filtering and model.total_count() == 4
    model.set_text_filter("m4a")  # o nome do arquivo também conta
    assert model.rowCount() == 4
    model.set_text_filter("")
    assert not model.filtering and model.rowCount() == 4


def test_typing_filters_list_and_updates_header(main):
    view, ctrl, _ = main
    QTest.keyClicks(view.filter_edit, "sol")
    assert titles(ctrl.processed) == ["Lugar Ao Sol"]
    assert view.processed_panel.header.text() == "Processadas (1 de 4)"
    assert view.pending_panel.view.model().rowCount() == 1  # a outra lista não é filtrada
    view.filter_edit.clear()
    assert ctrl.processed.rowCount() == 4
    assert view.processed_panel.header.text() == "Processadas (4)"


def test_no_results_message(main):
    view, ctrl, _ = main
    view.filter_edit.setText("xyz")
    assert ctrl.processed.rowCount() == 0
    assert view.processed_panel.header.text() == "Processadas (0 de 4)"
    assert view.processed_panel.view.empty_message() == "Nenhuma música com “xyz”"
    view.filter_edit.clear()
    assert view.processed_panel.view.empty_message() == ""


def test_esc_clears_filter(main):
    view, ctrl, _ = main
    view.filter_edit.setFocus()
    QTest.keyClicks(view.filter_edit, "night")
    assert ctrl.processed.rowCount() == 1
    QTest.keyClick(view.filter_edit, Qt.Key.Key_Escape)
    assert view.filter_edit.text() == "" and ctrl.processed.rowCount() == 4
    assert view.filter_edit.hasFocus()  # continua no campo, pronto para digitar


@pytest.mark.parametrize("how", ["tab", "ctrl_f", "click"])
def test_focus_selects_existing_text(main, how):
    view, _, _ = main
    view.filter_edit.setText("remastered")
    view.url_bar.setFocus()
    if how == "tab":
        view.pending_panel.view.setFocus()
        QTest.keyClick(view.pending_panel.view, Qt.Key.Key_Tab)
    elif how == "ctrl_f":
        QTest.keyClick(view.url_bar, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    else:
        QTest.mouseClick(view.filter_edit, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert view.filter_edit.hasFocus()
    assert view.filter_edit.selectedText() == "remastered"
    QTest.keyClicks(view.filter_edit, "sol")  # digitar substitui o filtro
    assert view.filter_edit.text() == "sol"


def test_focus_on_empty_filter_just_focuses(main):
    view, _, _ = main
    QTest.keyClick(view.url_bar, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert view.filter_edit.hasFocus() and view.filter_edit.selectedText() == ""


@pytest.mark.parametrize("key", [Qt.Key.Key_Down, Qt.Key.Key_Return])
def test_down_or_enter_go_to_first_match(main, key):
    view, ctrl, music = main
    played = []
    view.play_requested.disconnect()
    view.play_requested.connect(played.append)
    view.filter_edit.setFocus()
    QTest.keyClicks(view.filter_edit, "moves")
    QTest.keyClick(view.filter_edit, key)
    lv = view.processed_panel.view
    assert lv.hasFocus() and lv.currentIndex().data() == "Night Moves (Remastered 2011)"
    QTest.keyClick(lv, Qt.Key.Key_Return)
    assert played == [str(music / "Night Moves (Remastered 2011).m4a")]


def test_tab_order_passes_through_filter(main):
    view, _, _ = main
    view.pending_panel.view.setFocus()
    QTest.keyClick(view.pending_panel.view, Qt.Key.Key_Tab)
    assert view.filter_edit.hasFocus()
    QTest.keyClick(view.filter_edit, Qt.Key.Key_Tab)
    assert view.processed_panel.view.hasFocus()


def test_ctrl_f_does_nothing_with_a_page_open(main):
    from PySide6.QtWidgets import QWidget

    view, _, _ = main
    page = QWidget()
    view.show_page(page, "x")
    view.focus_filter()
    assert not view.filter_edit.hasFocus()
    view.show_library(page)
