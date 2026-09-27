import numpy as np
import pytest
from conftest import add_song, add_stems
from PySide6.QtCore import QObject, Signal

from karaoke.controllers import PlayerController
from karaoke.models import Lyrics, MusicLibraryModel, load_lyrics, parse_lrc
from karaoke.services import PlayerState
from karaoke.services.stem_player import BYTES_PER_FRAME, StemPlayer, mix
from karaoke.views import PlayerWindow
from karaoke.views.player_window import format_time

LRC = """[ar:Artista]
[ti:Música]
[00:05.00]Primeiro verso
[00:10.50]Segundo verso
[00:15.00][00:40.00]Refrão
[00:20.00]
"""


# ----------------------------------------------------------------- letra
def test_parse_lrc_orders_and_repeats_lines():
    lyrics = parse_lrc(LRC)
    assert lyrics.synced
    assert [(l.time, l.text) for l in lyrics.lines] == [
        (5.0, "Primeiro verso"),
        (10.5, "Segundo verso"),
        (15.0, "Refrão"),
        (20.0, ""),
        (40.0, "Refrão"),
    ]


def test_parse_lrc_offset():
    lyrics = parse_lrc("[offset:+500]\n[00:05.00]a\n[00:06.00]b\n")
    assert [l.time for l in lyrics.lines] == [4.5, 5.5]


@pytest.mark.parametrize(
    "seconds, index", [(0, -1), (4.99, -1), (5.0, 0), (12, 1), (39.9, 3), (41, 4), (999, 4)]
)
def test_line_at(seconds, index):
    assert parse_lrc(LRC).line_at(seconds) == index


def test_load_lyrics_plain_and_missing(tmp_path):
    txt = tmp_path / "a.txt"
    txt.write_text("Linha um\nLinha dois\n")
    lyrics = load_lyrics(txt)
    assert not lyrics.synced and [l.text for l in lyrics.lines] == ["Linha um", "Linha dois"]
    assert lyrics.line_at(3) == -1
    assert load_lyrics(None) == Lyrics()
    assert load_lyrics(tmp_path / "nao.lrc") == Lyrics()


# ----------------------------------------------------------------- áudio
def test_mix_applies_gains_and_clips():
    voc = np.array([[0.5, 0.5], [0.8, -0.8]], dtype="float32")
    inst = np.array([[0.25, -0.25], [0.8, -0.8]], dtype="float32")
    out = np.frombuffer(mix(voc, inst, 0.0, 1.0), dtype="<i2")
    assert list(out) == [8191, -8191, 26213, -26213]  # só instrumental
    out = np.frombuffer(mix(voc, inst, 1.0, 1.0), dtype="<i2")
    assert list(out[2:]) == [32767, -32767]            # saturou e foi limitado


def test_player_reads_mixed_chunks_in_order(qapp):
    player = StemPlayer()
    frames = 1000
    player._vocals = np.full((frames, 2), 0.5, dtype="float32")
    player._instrumental = np.full((frames, 2), 0.25, dtype="float32")
    player._frames, player._rate = frames, 1000
    player.set_vocal_volume(0.0)  # voz desligada

    chunk = player._read(400 * BYTES_PER_FRAME)
    assert len(chunk) == 400 * BYTES_PER_FRAME
    assert set(np.frombuffer(chunk, dtype="<i2")) == {8191}
    assert player._remaining_bytes() == 600 * BYTES_PER_FRAME

    player.set_vocal_volume(1.0)  # muda já no próximo bloco
    chunk = player._read(10_000 * BYTES_PER_FRAME)
    assert len(chunk) == 600 * BYTES_PER_FRAME
    assert set(np.frombuffer(chunk, dtype="<i2")) == {24575}
    assert player._read(100) == b""  # fim


def test_player_seek_while_stopped(qapp):
    player = StemPlayer()
    player._frames, player._rate = 44100 * 10, 44100
    positions = []
    player.position_changed.connect(positions.append)
    player.seek(3.5)
    assert player._cursor == int(3.5 * 44100) and positions == [3.5]
    player.seek(99)
    assert player._cursor == player._frames


def test_format_time():
    assert [format_time(t) for t in (0, 9.9, 65, 600)] == ["0:00", "0:09", "1:05", "10:00"]


# ------------------------------------------------------------ controlador
class FakePlayer(QObject):
    loaded = Signal(float)
    load_failed = Signal(str)
    position_changed = Signal(float)
    state_changed = Signal(object)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.calls = []
        self.pos = 0.0
        self.volumes = {}
        self.state = PlayerState.STOPPED

    def load(self, vocals, instrumental):
        self.calls.append(("load", vocals.name, instrumental.name))

    def play(self):
        self.calls.append(("play",))
        self.state_changed.emit(PlayerState.PLAYING)

    def toggle(self):
        self.calls.append(("toggle",))

    def stop(self):
        self.calls.append(("stop",))

    def seek(self, seconds):
        self.calls.append(("seek", seconds))

    def position(self):
        return self.pos

    def set_vocal_volume(self, v):
        self.volumes["voz"] = v

    def set_instrumental_volume(self, v):
        self.volumes["inst"] = v


@pytest.fixture
def song(qapp, dirs):
    music, separated = dirs
    add_song(music, "Música [abcdefghijk].webm")
    add_stems(separated, "Música [abcdefghijk]")
    letras = music.parent / "letras"
    letras.mkdir()
    (letras / "Música [abcdefghijk].lrc").write_text(LRC)
    model = MusicLibraryModel(music, separated)
    model.scan()
    return model.songs()[0]


def test_player_controller_flow(song):
    view, player = PlayerWindow(), FakePlayer()
    ctrl = PlayerController(song, view, player)
    ctrl.start()
    assert player.calls == [("load", "vocais.flac", "instrumental.flac")]
    assert view.lyrics_view.line_count() == 5 and not view.play_button.isEnabled()
    assert player.volumes == {"voz": pytest.approx(0.3), "inst": pytest.approx(1.0)}

    player.loaded.emit(60.0)
    assert ("play",) not in player.calls  # não toca sozinho
    assert view.play_button.isEnabled() and view.play_button.toolTip().startswith("Tocar")
    view.play_button.click()
    assert player.calls[-1] == ("toggle",)
    player.state_changed.emit(PlayerState.PLAYING)
    assert view.play_button.toolTip().startswith("Pausar")

    player.position_changed.emit(11.0)
    assert view._current_line == 1
    assert view.lyrics_view.line_item(1).font().bold()
    assert view.time_label.text() == "0:11 / 1:00"

    view.vocal_volume.slider.setValue(30)
    assert player.volumes["voz"] == pytest.approx(0.3)

    view.lyrics_view.itemClicked.emit(view.lyrics_view.line_item(2))  # clicar no verso
    assert player.calls[-1] == ("seek", 15.0)

    player.pos = 20.0
    view.seek_relative_requested.emit(5)
    assert player.calls[-1] == ("seek", 25.0)

    player.state_changed.emit(PlayerState.PAUSED)
    closed = []
    ctrl.closed.connect(lambda: closed.append(1))
    view.close()  # pausado: fecha sem perguntar
    assert closed == [1] and ("stop",) in player.calls


def test_double_click_opens_player_only_for_processed(qapp, dirs, monkeypatch):
    from test_controller import make

    import karaoke.controllers.app_controller as app_module

    opened = []

    class Recorder:
        def __init__(self, song, parent=None):
            opened.append(song.title)
            self.closed = type("S", (), {"connect": lambda *a: None})()

        def start(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(app_module, "PlayerController", Recorder)
    music, separated = dirs
    feita = add_song(music, "feita.m4a")
    nova = add_song(music, "nova.m4a")
    add_stems(separated, "feita")
    (music.parent / "letras").mkdir()
    (music.parent / "letras" / "feita.lrc").write_text(LRC)
    view, ctrl = make(dirs)
    ctrl.refresh_library()

    view.processed_panel.view.doubleClicked.emit(ctrl.processed.index_of(feita))
    assert opened == ["feita"]
    ctrl.open_player(str(nova))  # ainda não processada: ignora
    assert opened == ["feita"]


# ------------------------------------------------------------- carga
def _write_stems(folder, seconds=0.5, rate=8000):
    import soundfile as sf

    folder.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0, seconds, int(seconds * rate), endpoint=False)
    tone = (0.2 * np.sin(2 * np.pi * 440 * t)).astype("float32")
    sf.write(folder / "vocais.flac", np.column_stack([tone, tone]), rate)
    sf.write(folder / "instrumental.flac", np.column_stack([tone, -tone]), rate)
    return folder / "vocais.flac", folder / "instrumental.flac"


def _spin(ms):
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def no_sink(monkeypatch):
    import karaoke.services.stem_player as sp

    monkeypatch.setattr(sp, "has_audio_output", lambda: True)
    monkeypatch.setattr(StemPlayer, "_setup_sink", lambda self, d: None)


def test_load_delivers_data_on_main_thread(qapp, tmp_path, no_sink):
    vocals, inst = _write_stems(tmp_path)
    player = StemPlayer()
    durations = []
    player.loaded.connect(durations.append)
    player.load(vocals, inst)
    _spin(1000)
    assert durations == [pytest.approx(0.5)]
    assert player._frames == 4000 and player._rate == 8000


def test_closing_player_during_load_raises_nothing(qapp, tmp_path, no_sink):
    import threading

    vocals, inst = _write_stems(tmp_path)
    errors = []
    previous = threading.excepthook
    threading.excepthook = lambda args: errors.append(args.exc_value)
    try:
        player = StemPlayer()
        player.load(vocals, inst)
        player.deleteLater()  # fecha antes de terminar de carregar
        _spin(1000)
    finally:
        threading.excepthook = previous
    assert errors == []


def test_only_latest_load_is_applied(qapp, tmp_path, no_sink):
    first = _write_stems(tmp_path / "a", seconds=0.5)
    second = _write_stems(tmp_path / "b", seconds=0.25)
    player = StemPlayer()
    durations = []
    player.loaded.connect(durations.append)
    player.load(*first)
    player.load(*second)  # outra música antes da primeira carregar
    _spin(1000)
    assert durations == [pytest.approx(0.25)]
    assert player._frames == 2000


# ------------------------------------------------------------- janela
def _click_at_fraction(slider, fraction):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    x = int(slider.width() * fraction)
    QTest.mouseClick(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, slider.height() // 2))


def test_click_on_bars_jumps_to_clicked_point(qapp):
    view = PlayerWindow()
    view.resize(800, 600)
    view.show()
    _spin(50)
    voice = view.vocal_volume.slider
    assert voice.value() == 30  # padrão

    _click_at_fraction(voice, 0.9)
    assert voice.value() >= 85  # foi até o clique, não só +10
    _click_at_fraction(voice, 0.1)
    assert voice.value() <= 15

    seeks = []
    view.seek_requested.connect(seeks.append)
    view.set_duration(200.0)
    _click_at_fraction(view.position_slider, 0.75)
    assert seeks and seeks[-1] == pytest.approx(150, abs=8)


def test_lyrics_current_line_stays_centered(qapp):
    view = PlayerWindow()
    view.resize(700, 600)
    view.show()
    lrc = "\n".join(f"[00:{i * 2:02d}.00]Verso {i}" for i in range(25))
    view.set_lyrics(parse_lrc(lrc))
    _spin(50)
    lv = view.lyrics_view
    middle = lv.viewport().height() / 2

    def center_of(i):
        return lv.visualItemRect(lv.line_item(i)).center().y()

    assert abs(center_of(0) - middle) < 30  # antes de começar: 1º verso no meio
    for index in (0, 12, 24):              # início, meio e último verso
        view.highlight_line(index)
        _spin(SCROLL_MS + 150)
        assert abs(center_of(index) - middle) < 30, index


from PySide6.QtCore import Qt  # noqa: E402

from karaoke.views.player_window import SCROLL_ANIMATION_MS as SCROLL_MS  # noqa: E402


# ------------------------------------------------------------ confirmações
@pytest.fixture
def answers(monkeypatch):
    """Respostas simuladas para os diálogos de confirmação."""
    from karaoke.views import dialogs

    state = {"answer": False, "asked": []}

    def fake_confirm(parent, title, text):
        state["asked"].append(title)
        return state["answer"]

    monkeypatch.setattr(dialogs, "confirm", fake_confirm)
    return state


def _playing_controller(song):
    player = FakePlayer()
    ctrl = PlayerController(song, PlayerWindow(), player)
    ctrl.start()
    player.loaded.emit(60.0)
    player.state_changed.emit(PlayerState.PLAYING)
    player.state = PlayerState.PLAYING
    return ctrl, player


def test_player_window_asks_before_closing_while_playing(song, answers):
    ctrl, player = _playing_controller(song)
    closed = []
    ctrl.closed.connect(lambda: closed.append(1))

    answers["answer"] = False
    ctrl.view.close()
    assert answers["asked"] == ["Fechar o player"]
    assert closed == [] and ctrl.view.isVisible()  # cancelou: continua aberto

    answers["answer"] = True
    ctrl.view.close()
    assert closed == [1] and ("stop",) in player.calls


def test_main_window_closes_player_and_asks_if_playing(qapp, dirs, answers, monkeypatch):
    from test_controller import make

    music, separated = dirs
    add_song(music, "a.m4a")
    add_stems(separated, "a")
    (music.parent / "letras").mkdir()
    (music.parent / "letras" / "a.lrc").write_text(LRC)
    view, app_ctrl = make(dirs)
    app_ctrl.refresh_library()
    view.show()

    player = FakePlayer()
    player.state = PlayerState.PAUSED
    monkeypatch.setattr(
        "karaoke.controllers.app_controller.PlayerController",
        lambda song, parent=None: PlayerController(song, PlayerWindow(), player, parent),
    )
    app_ctrl.open_player(str(music / "a.m4a"))
    player_view = app_ctrl.player.view

    # Pausado: fecha tudo sem perguntar
    assert view.close()
    assert answers["asked"] == [] and app_ctrl.player is None
    assert not player_view.isVisible()

    # Tocando: pergunta; "Não" mantém as duas janelas abertas
    view.show()
    app_ctrl.open_player(str(music / "a.m4a"))
    player.state = PlayerState.PLAYING
    player.state_changed.emit(PlayerState.PLAYING)
    answers["answer"] = False
    assert not view.close()
    assert answers["asked"] == ["Fechar o Karaokê"]
    assert view.isVisible() and app_ctrl.player is not None

    # "Sim": fecha a principal e o player, sem uma segunda pergunta do player
    answers["answer"] = True
    player_view = app_ctrl.player.view
    assert view.close()
    assert answers["asked"] == ["Fechar o Karaokê", "Fechar o Karaokê"]
    assert app_ctrl.player is None and not player_view.isVisible()


# ------------------------------------------------------- sincronização manual
def test_offset_roundtrip_and_first_sung_line(tmp_path):
    from karaoke.models import write_lrc_offset

    path = tmp_path / "a.lrc"
    path.write_text("[ar:X]\n[00:02.00]\n[00:05.00]Primeiro\n[00:10.00]Segundo\n")
    lyrics = load_lyrics(path)
    assert lyrics.first_sung_line() == 1 and lyrics.offset == 0

    write_lrc_offset(path, -1.25)  # atrasa 1,25 s
    lyrics = load_lyrics(path)
    assert path.read_text().splitlines()[0] == "[offset:-1250]"
    assert [l.time for l in lyrics.lines] == [3.25, 6.25, 11.25]
    assert lyrics.offset == -1.25

    write_lrc_offset(path, 0.5)  # substitui, não acumula tags
    assert path.read_text().count("[offset:") == 1
    assert load_lyrics(path).lines[1].time == 4.5

    write_lrc_offset(path, 0)  # zero remove a tag
    assert "[offset:" not in path.read_text()


def test_offset_tag_anywhere_applies_to_all_lines():
    lyrics = parse_lrc("[00:05.00]a\n[offset:+1000]\n[00:06.00]b\n[00:07.00]c\n")
    assert [l.time for l in lyrics.lines] == [4.0, 5.0, 6.0]


def _open_ready(song):
    player = FakePlayer()
    view = PlayerWindow()
    ctrl = PlayerController(song, view, player)
    ctrl.start()
    player.loaded.emit(60.0)
    return ctrl, view, player


def test_manual_sync_shifts_and_saves(song):
    ctrl, view, player = _open_ready(song)
    lrc_path = song.lyrics_path
    assert view.sync_button.isEnabled()

    view.sync_button.click()  # entra no modo de sincronização
    assert view.in_sync_mode and view.sync_button.text() == "Cancelar"
    first = ctrl.lyrics.first_sung_line()
    assert view.lyrics_view.line_item(first).text().startswith("▶")

    player.position_changed.emit(30.0)  # a letra fica parada esperando o clique
    assert view._current_line == -1

    # verso errado: só avisa
    player.pos = 6.0
    view.lyrics_view.itemClicked.emit(view.lyrics_view.line_item(first + 1))
    assert view.in_sync_mode and "primeiro verso" in view.lyrics_note.text()
    assert "[offset:" not in lrc_path.read_text()

    # primeiro verso (tempo 5,0 s no LRC) clicado aos 6,2 s: atrasa 1,2 s
    player.pos = 6.2
    view.lyrics_view.itemClicked.emit(view.lyrics_view.line_item(first))
    assert not view.in_sync_mode and view.sync_button.text() == "Sincronizar"
    assert ctrl.lyrics.lines[first].time == pytest.approx(6.2)
    assert ctrl.lyrics.lines[first + 1].time == pytest.approx(11.7)
    assert "[offset:-1200]" in lrc_path.read_text()
    assert "atrasada em 1,20 s" in view.lyrics_note.text()
    assert view._current_line == first  # voltou a acompanhar a música
    assert ("seek", 5.0) not in player.calls  # clique no modo não faz seek

    # reabrir a música mantém o ajuste
    assert load_lyrics(lrc_path).lines[first].time == pytest.approx(6.2)

    # sincronizar de novo compõe com o ajuste anterior
    view.sync_button.click()
    player.pos = 6.0
    view.lyrics_view.itemClicked.emit(view.lyrics_view.line_item(first))
    assert ctrl.lyrics.lines[first].time == pytest.approx(6.0)
    assert "[offset:-1000]" in lrc_path.read_text()


def test_sync_can_be_cancelled_and_needs_synced_lyrics(song, tmp_path):
    ctrl, view, player = _open_ready(song)
    view.sync_button.click()
    assert view.in_sync_mode
    view.sync_button.click()  # "Cancelar"
    assert not view.in_sync_mode and "[offset:" not in song.lyrics_path.read_text()
    assert not any(view.lyrics_view.line_item(i).text().startswith("▶") for i in range(5))

    view.set_lyrics(load_lyrics(None))  # sem letra: botão desativado
    assert not view.sync_button.isEnabled()


# ---------------------------------------------------------- tamanho da letra
@pytest.fixture
def fresh_font_setting():
    from karaoke.views.player_window import _settings

    _settings().remove("player/lyrics_font_size")
    yield
    _settings().remove("player/lyrics_font_size")


def test_font_buttons_change_size_and_keep_line_centered(qapp, fresh_font_setting):
    from karaoke.views.player_window import (
        DEFAULT_LYRICS_FONT_SIZE,
        MAX_LYRICS_FONT_SIZE,
        MIN_LYRICS_FONT_SIZE,
        SCROLL_ANIMATION_MS,
    )

    view = PlayerWindow()
    view.resize(800, 640)
    view.show()
    lrc = "\n".join(f"[00:{i * 2:02d}.00]Verso {i}" for i in range(20))
    view.set_lyrics(parse_lrc(lrc))
    view.highlight_line(10)
    _spin(SCROLL_ANIMATION_MS + 100)
    lv = view.lyrics_view
    assert view.font_size == DEFAULT_LYRICS_FONT_SIZE == 20
    assert lv.line_item(3).font().pointSize() == 20
    assert lv.line_item(10).font().pointSize() == 26  # verso atual 30% maior

    view.font_larger_button.click()
    view.font_larger_button.click()
    assert view.font_size == 24
    assert lv.line_item(3).font().pointSize() == 24
    assert lv.line_item(10).font().pointSize() == 31 and lv.line_item(10).font().bold()
    middle = lv.viewport().height() / 2
    assert abs(lv.visualItemRect(lv.line_item(10)).center().y() - middle) < 30

    view.font_smaller_button.click()
    assert view.font_size == 22

    view.set_font_size(1000)  # limites
    assert view.font_size == MAX_LYRICS_FONT_SIZE and not view.font_larger_button.isEnabled()
    view.set_font_size(0)
    assert view.font_size == MIN_LYRICS_FONT_SIZE and not view.font_smaller_button.isEnabled()
    assert view.font_larger_button.isEnabled()


def test_font_size_is_remembered(qapp, fresh_font_setting):
    first = PlayerWindow()
    first.set_font_size(30)
    second = PlayerWindow()  # próxima vez que o player abrir
    assert second.font_size == 30
    second.set_lyrics(parse_lrc("[00:01.00]a\n[00:02.00]b\n[00:03.00]c\n"))
    assert second.lyrics_view.line_item(0).font().pointSize() == 30


def test_font_size_in_sync_mode_keeps_marked_verse_big(qapp, fresh_font_setting):
    view = PlayerWindow()
    view.set_lyrics(parse_lrc("[00:01.00]a\n[00:02.00]b\n[00:03.00]c\n"))
    view.set_sync_mode(True, 0)
    view.change_font_size(4)
    assert view.lyrics_view.line_item(0).font().pointSize() == round(24 * 1.3)
    assert view.lyrics_view.line_item(0).text().startswith("▶")



# ------------------------------------------------------------- tela cheia
def test_fullscreen_toggle_button_f11_and_escape(qapp):
    from PySide6.QtTest import QTest

    view = PlayerWindow()
    view.resize(800, 600)
    view.show()
    assert not view.is_fullscreen and not view.fullscreen_button.isChecked()

    view.fullscreen_button.click()
    assert view.is_fullscreen and view.fullscreen_button.isChecked()
    assert "Sair" in view.fullscreen_button.toolTip()

    view._on_escape()  # Esc sai da tela cheia
    assert not view.is_fullscreen and not view.fullscreen_button.isChecked()

    view.toggle_fullscreen()  # F11
    assert view.is_fullscreen
    view.toggle_fullscreen()
    assert not view.is_fullscreen


def test_escape_cancels_sync_before_leaving_fullscreen(qapp):
    view = PlayerWindow()
    view.show()
    view.set_lyrics(parse_lrc("[00:01.00]a\n[00:02.00]b\n[00:03.00]c\n"))
    # o PlayerController liga o botão ao modo de sincronização assim:
    view.sync_mode_toggled.connect(lambda active: view.set_sync_mode(active, 0))
    view.set_fullscreen(True)
    view.sync_button.click()
    assert view.in_sync_mode
    view._on_escape()
    assert not view.in_sync_mode and view.is_fullscreen  # 1º Esc: só cancela a sincronização
    view._on_escape()
    assert not view.is_fullscreen                         # 2º Esc: sai da tela cheia


def test_leaving_fullscreen_restores_maximized(qapp):
    view = PlayerWindow()
    view.showMaximized()
    view.set_fullscreen(True)
    view.set_fullscreen(False)
    assert view.isMaximized() and not view.is_fullscreen
