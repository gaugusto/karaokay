"""A divisória entre "A processar" e "Processadas" é lembrada entre execuções."""

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from karaoke.views import MainWindow
from karaoke.views.main_window import DEFAULT_SPLITTER_RATIO, SPLITTER_KEY
from karaoke.views.settings import settings


@pytest.fixture(autouse=True)
def clean():
    settings().remove(SPLITTER_KEY)
    yield
    settings().remove(SPLITTER_KEY)


def open_window(size=(1100, 760)):
    window = MainWindow()
    window.resize(*size)
    window.show()
    QTest.qWaitForWindowExposed(window)
    QApplication.processEvents()
    return window


def drag_to(window, ratio):
    """Como o usuário arrastando: move a alça e emite splitterMoved."""
    top, bottom = window.splitter.sizes()
    handle = window.splitter.handle(1)
    y = round((top + bottom + handle.height()) * ratio)
    window.splitter.moveSplitter(y, 1)  # (protegido no C++; exposto pelo PySide)


def test_default_position_without_saved_value(qapp):
    window = open_window()
    assert window.splitter_ratio() == pytest.approx(DEFAULT_SPLITTER_RATIO, abs=0.02)
    window.close()


def test_position_is_saved_and_restored(qapp):
    window = open_window()
    drag_to(window, 0.7)
    assert window._save_splitter_timer.isActive()  # grava quando o arrasto para
    QTest.qWait(500)
    saved = float(settings().value(SPLITTER_KEY))
    assert saved == pytest.approx(0.7, abs=0.03)
    window.close()

    again = open_window()
    assert again.splitter_ratio() == pytest.approx(saved, abs=0.01)
    again.close()


def test_restored_proportion_survives_other_window_size(qapp):
    settings().setValue(SPLITTER_KEY, 0.25)
    window = open_window((900, 600))
    assert window.splitter_ratio() == pytest.approx(0.25, abs=0.02)
    window.resize(1300, 1000)  # ex.: janela maximizada
    QApplication.processEvents()
    assert window.splitter_ratio() == pytest.approx(0.25, abs=0.03)
    window.close()


def test_close_saves_pending_drag_immediately(qapp):
    window = open_window()
    drag_to(window, 0.35)
    window.close()  # fechou antes do temporizador
    assert float(settings().value(SPLITTER_KEY)) == pytest.approx(0.35, abs=0.03)


@pytest.mark.parametrize("value", ["lixo", 5, -1])
def test_invalid_or_extreme_values_are_tamed(qapp, value):
    settings().setValue(SPLITTER_KEY, value)
    window = open_window()
    ratio = window.splitter_ratio()
    assert 0.03 < ratio < 0.97
    if value == "lixo":
        assert ratio == pytest.approx(DEFAULT_SPLITTER_RATIO, abs=0.02)
    window.close()
