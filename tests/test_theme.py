import pytest
from conftest import add_song, add_stems
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from karaoke.models import LyricsState, SongState
from karaoke.views import theme
from karaoke.views.song_delegate import pending_badge, processed_badge, queue_position


@pytest.fixture
def themed(qapp):
    """Aplica o tema durante o teste e restaura o estado depois."""
    style, palette, sheet, font = qapp.style().name(), qapp.palette(), qapp.styleSheet(), qapp.font()
    theme.apply_theme(qapp)
    yield qapp
    qapp.setStyleSheet(sheet)
    qapp.setPalette(palette)
    qapp.setFont(font)
    qapp.setStyle(style)


def test_theme_is_dark(themed):
    from PySide6.QtGui import QPalette

    window = themed.palette().color(QPalette.ColorRole.Window)
    text = themed.palette().color(QPalette.ColorRole.Text)
    assert window.lightness() < 40 < 200 < text.lightness()
    assert themed.palette().color(QPalette.ColorRole.Highlight).name() == theme.Colors.ACCENT.lower()
    assert "QPushButton#playButton" in themed.styleSheet()


def test_badges(qapp, dirs):
    from karaoke.models import MusicLibraryModel

    music, separated = dirs
    add_song(music, "a.m4a")
    model = MusicLibraryModel(music, separated)
    model.scan()
    song = model.songs()[0]
    assert pending_badge(song) == ("aguardando", theme.Colors.TEXT_SECONDARY)
    assert queue_position(song, 0) is None  # fora da fila: sem número
    song.state = SongState.QUEUED
    assert queue_position(song, 2) == 3
    song.state, song.progress = SongState.SEPARATING, None
    assert pending_badge(song)[0] == "processando…"
    song.state = SongState.FAILED
    assert pending_badge(song) == ("falha", theme.Colors.DANGER)
    for state, expected in [
        (LyricsState.SYNCED, theme.Colors.SUCCESS),
        (LyricsState.PLAIN, theme.Colors.WARNING),
        (LyricsState.FAILED, theme.Colors.DANGER),
    ]:
        song.lyrics_state = state
        assert processed_badge(song)[1] == expected


def test_jump_sliders_still_work_with_theme(themed):
    from karaoke.views import PlayerWindow

    view = PlayerWindow()
    view.resize(900, 700)
    view.show()
    slider = view.vocal_volume.slider
    QTest.mouseClick(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(int(slider.width() * 0.8), slider.height() // 2))
    assert slider.value() >= 75
    assert view.play_button.width() == 56


def test_lists_render_cards_without_errors(themed, dirs):
    from test_controller import make

    music, separated = dirs
    for i, name in enumerate(["processando", "fila", "falha"]):
        add_song(music, f"{name}.m4a", mtime=i)
    add_song(music, "pronta.m4a")
    add_stems(separated, "pronta")
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    ctrl.separator.started.emit(str(music / "processando.m4a"))
    ctrl.separator.progress.emit(str(music / "processando.m4a"), 55)
    ctrl.separator.failed.emit(str(music / "falha.m4a"), "erro")
    view.resize(900, 700)
    view.show()
    image = view.grab().toImage()
    assert not image.isNull()
    # o cartão tem a altura prevista (58 + espaço)
    index = ctrl.pending.index(0, 0)
    assert view.pending_panel.view.visualRect(index).height() == 64
