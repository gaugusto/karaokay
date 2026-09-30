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
    theme.apply_theme(qapp, theme.DARK)
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


def test_switching_theme_updates_open_windows(themed):
    from dataclasses import replace

    from PySide6.QtGui import QPalette

    from pathlib import Path

    from karaoke.models import Song, parse_lrc
    from karaoke.views import PlayerWindow
    from karaoke.views.main_window import FilterEdit

    view = PlayerWindow()
    view.set_lyrics(parse_lrc("[00:01.00]primeiro\n[00:02.00]segundo\n"))
    view.highlight_line(0)
    filter_edit = FilterEdit()
    old_play = view.play_button.icon().pixmap(26, 26).toImage()
    old_search = filter_edit.actions()[0].icon().pixmap(16, 16).toImage()
    received = []
    theme.theme_changed.changed.connect(received.append)

    green = replace(theme.DARK, name="teste", palette=replace(
        theme.DARK.palette, ACCENT="#00FF00", ACCENT_HOVER="#00EE00", ON_ACCENT="#000000",
        SUCCESS="#123456", TEXT_MUTED="#FF00FF"))
    theme.apply_theme(themed, green)

    assert received == [green] and theme.current_theme() is green
    assert theme.Colors.ACCENT == "#00FF00"
    assert themed.palette().color(QPalette.ColorRole.Highlight).name() == "#00ff00"
    assert "#00FF00" in themed.styleSheet() and theme.DARK.palette.ACCENT not in themed.styleSheet()
    song = Song(Path("a.m4a"), Path("a"), lyrics_state=LyricsState.SYNCED)
    assert processed_badge(song)[1] == "#123456"
    assert view.lyrics_view.line_item(0).foreground().color().name() == "#00ee00"
    assert view.play_button.icon().pixmap(26, 26).toImage() != old_play
    assert filter_edit.actions()[0].icon().pixmap(16, 16).toImage() != old_search
    theme.theme_changed.changed.disconnect(received.append)


def _luminance(hex_code: str) -> float:
    from PySide6.QtGui import QColor

    c = QColor(hex_code)

    def channel(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(c.red()) + 0.7152 * channel(c.green()) + 0.0722 * channel(c.blue())


def test_accent_themes_only_change_the_accent():
    from dataclasses import fields

    accent_keys = {"ACCENT", "ACCENT_HOVER", "ACCENT_PRESSED", "ACCENT_DIM", "SURFACE_SELECTED"}
    assert len(theme.ACCENT_THEMES) == 5
    assert len({t.palette.ACCENT for t in theme.ACCENT_THEMES}) == 5
    assert set(theme.THEMES) == {t.name for t in theme.ACCENT_THEMES}
    for t in theme.ACCENT_THEMES:
        changed = {f.name for f in fields(t.palette)
                   if getattr(t.palette, f.name) != getattr(theme.DARK.palette, f.name)}
        assert changed <= accent_keys
        assert (t.blobs, t.veil_alpha, t.card_alpha) == (theme.DARK.blobs, theme.DARK.veil_alpha, theme.DARK.card_alpha)
        light, dark = sorted([_luminance(t.palette.ON_ACCENT), _luminance(t.palette.ACCENT)], reverse=True)
        assert (light + 0.05) / (dark + 0.05) >= 3, t.name


def test_next_theme_cycles():
    seen = [theme.DARK]
    for _ in range(len(theme.ACCENT_THEMES)):
        seen.append(theme.next_theme(seen[-1]))
    assert seen[:-1] == list(theme.ACCENT_THEMES) and seen[-1] is theme.DARK
    assert theme.next_theme(theme.Theme("outro", theme.DARK.palette, (), 0, 0)) is theme.DARK


def test_theme_button_cycles_accent_and_remembers(themed):
    from karaoke.views import MainWindow
    from karaoke.views.settings import THEME_KEY, saved_theme_name, settings

    settings().remove(THEME_KEY)
    try:
        window = MainWindow()
        accents = []
        for t in theme.ACCENT_THEMES[1:] + theme.ACCENT_THEMES[:1]:
            window.theme_button.click()
            assert theme.current_theme() is t
            assert saved_theme_name() == t.name
            assert t.name in window.theme_button.toolTip()
            accents.append(theme.Colors.ACCENT)
        assert len(set(accents)) == 5 and theme.current_theme() is theme.DARK
    finally:
        settings().remove(THEME_KEY)
