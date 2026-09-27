"""Sincronização automática da letra com os vocais."""

import numpy as np
import pytest
from conftest import add_song, add_stems
from PySide6.QtCore import QObject, Signal

from karaoke.models import LyricsState, load_lyrics, parse_lrc, retime_lrc
from karaoke.services.auto_sync import SyncResult, align, vocal_activity

RATE = 8000


def make_lyrics(seed=1, lines=24):
    rng = np.random.default_rng(seed)
    times, t = [], 12.0
    for i in range(lines):
        times.append(round(t, 2))
        t += rng.uniform(3.0, 5.0) + (12 if i == lines // 2 else 0)  # instrumental no meio
    text = "\n".join(f"[{int(x // 60):02d}:{x % 60:05.2f}]verso {i}" for i, x in enumerate(times))
    return times, text


def sing(times, offset=0.0, scale=1.0, jitter=0.0, seed=2):
    """Vocais sintéticos: um trecho "cantado" por verso, com ruído de fundo."""
    rng = np.random.default_rng(seed)
    duration = times[-1] * scale + offset + 20
    audio = rng.normal(0, 0.003, int(duration * RATE))
    real = []
    for i, x in enumerate(times):
        start = x * scale + offset + rng.normal(0, jitter)
        nxt = times[i + 1] * scale + offset if i + 1 < len(times) else start + 3
        end = start + (nxt - start) * rng.uniform(0.6, 0.85)
        a, b = int(start * RATE), int(end * RATE)
        tt = np.arange(b - a) / RATE
        audio[a:b] += 0.2 * np.sin(2 * np.pi * rng.uniform(180, 400) * tt) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * tt))
        real.append(start)
    return audio.astype("float32"), real


# ------------------------------------------------------------------ algoritmo
@pytest.mark.parametrize("offset, scale", [(7.3, 1.02), (-4.0, 1.0), (35.0, 0.98)])
def test_align_recovers_offset_and_tempo(offset, scale):
    times, text = make_lyrics()
    audio, real = sing(times, offset, scale, jitter=0.25)
    result = align(parse_lrc(text), vocal_activity(audio, RATE))
    assert result.ok and result.confidence_label in ("alta", "média")
    assert abs(result.offset - offset) < 1.0 and result.scale == pytest.approx(scale)
    before = np.mean(np.abs(np.array(times) - np.array(real)))
    after = np.mean(np.abs(np.array(result.new_times) - np.array(real)))
    assert before > 3.5 and after < 0.1  # de segundos de erro para centésimos
    assert all(b > a for a, b in zip(result.new_times, result.new_times[1:]))  # ordem mantida


def test_align_refuses_other_song_and_silence():
    times, text = make_lyrics()
    lyrics = parse_lrc(text)
    for seed in range(5):  # vocais de outra música: versos em outros lugares
        other = sorted(np.random.default_rng(300 + seed).uniform(5, 150, 24))
        audio, _ = sing(list(other), seed=seed)
        assert not align(lyrics, vocal_activity(audio, RATE)).ok, seed
    noise = np.random.default_rng(9).normal(0, 0.003, 150 * RATE).astype("float32")
    result = align(lyrics, vocal_activity(noise, RATE))
    assert not result.ok and result.new_times == result.old_times


def test_retime_keeps_headers_and_bakes_offset():
    text = "[ar:Artista]\n[ti:Música]\n[offset:+500]\n[00:10.50]Um\n[00:20.00][01:00.00]Refrão\n\n[00:30.00]\n"
    lyrics = parse_lrc(text)
    assert [l.time for l in lyrics.lines] == [10.0, 19.5, 29.5, 59.5]
    mapping = {10.0: 12.0, 19.5: 21.25, 29.5: 31.0, 59.5: 61.5}
    out = retime_lrc(text, mapping)
    assert out.splitlines() == [
        "[ar:Artista]", "[ti:Música]", "[00:12.00]Um", "[00:21.25][01:01.50]Refrão", "", "[00:31.00]",
    ]
    assert [l.time for l in parse_lrc(out).lines] == [12.0, 21.25, 31.0, 61.5]


# ----------------------------------------------------------- controlador
class FakeAutoSync(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.runs = []

    def run(self, song_path, vocals, lyrics):
        self.runs.append((str(song_path), vocals.name, len(lyrics.lines)))


LRC = "[ar:X]\n[00:05.00]um\n[00:10.00]dois\n[00:15.00]três\n"


@pytest.fixture
def app(qapp, dirs, monkeypatch):
    from test_controller import FakeDownloader, FakeSeparator

    from karaoke.controllers import AppController
    from karaoke.models import MusicLibraryModel
    from karaoke.views import MainWindow, dialogs

    informed = []
    monkeypatch.setattr(dialogs, "inform", lambda parent, title, text: informed.append(text))
    music, separated = dirs
    add_song(music, "a.m4a")
    add_stems(separated, "a")
    add_song(music, "semletra.m4a")
    add_stems(separated, "semletra")
    letras = music.parent / "letras"
    letras.mkdir()
    (letras / "a.lrc").write_text(LRC)
    view = MainWindow()
    ctrl = AppController(view, model=MusicLibraryModel(music, separated), downloader=FakeDownloader(),
                         separator=FakeSeparator(), auto_sync=FakeAutoSync())
    ctrl.refresh_library()
    return view, ctrl, music, letras, informed


def result(confidence):
    return SyncResult(offset=2.0, scale=1.0, confidence=confidence,
                      old_times=[5.0, 10.0, 15.0], new_times=[7.0, 12.1, 17.0], snapped=3)


def test_menu_offers_auto_sync_only_for_synced_lyrics(app):
    view, ctrl, music, letras, _ = app
    menu = view.build_processed_menu(ctrl.processed.index_of(music / "a.m4a"))
    letra = next(a.menu() for a in menu.actions() if a.text() == "Letra")
    texts = {a.text(): a.isEnabled() for a in letra.actions() if a.text()}
    assert texts["Sincronizar automaticamente com os vocais"] is True
    assert texts["Restaurar letra original"] is False  # ainda não há cópia
    menu = view.build_processed_menu(ctrl.processed.index_of(music / "semletra.m4a"))
    letra = next(a.menu() for a in menu.actions() if a.text() == "Letra")
    auto = next(a for a in letra.actions() if a.text().startswith("Sincronizar"))
    assert not auto.isEnabled() and "precisa de letra sincronizada" in auto.text()


def test_auto_sync_applies_backs_up_and_restores(app):
    view, ctrl, music, letras, informed = app
    path = str(music / "a.m4a")
    view.auto_sync_requested.emit(path)
    assert ctrl.auto_sync.runs == [(path, "vocais.flac", 3)]
    view.auto_sync_requested.emit(path)  # já rodando: não repete
    assert len(ctrl.auto_sync.runs) == 1

    ctrl.auto_sync.finished.emit(path, result(0.9))
    assert (letras / "a.lrc").read_text().splitlines() == ["[ar:X]", "[00:07.00]um", "[00:12.10]dois", "[00:17.00]três"]
    assert (letras / "a.original.lrc").read_text() == LRC
    assert "deslocamento +2,0 s" in view.statusBar().currentMessage()
    assert "confiança alta" in view.statusBar().currentMessage()

    ctrl.auto_sync_lyrics(path)  # 2ª vez: a cópia continua sendo a original
    ctrl.auto_sync.finished.emit(path, SyncResult(1.0, 1.0, 0.9, [7.0, 12.1, 17.0], [8.0, 13.0, 18.0], 3))
    assert (letras / "a.original.lrc").read_text() == LRC

    view.restore_lyrics_requested.emit(path)
    assert (letras / "a.lrc").read_text() == LRC
    assert not (letras / "a.original.lrc").exists()
    assert informed == []


def test_low_confidence_changes_nothing(app):
    view, ctrl, music, letras, informed = app
    path = str(music / "a.m4a")
    ctrl.auto_sync_lyrics(path)
    ctrl.auto_sync.finished.emit(path, result(0.3))
    assert (letras / "a.lrc").read_text() == LRC and not (letras / "a.original.lrc").exists()
    assert len(informed) == 1 and "confiança 30%" in informed[0] and "não foi alterada" in informed[0]


def test_new_lyrics_or_delete_remove_backup(app, monkeypatch):
    from karaoke.services.lyrics import LyricsResult, save_lyrics
    from karaoke.views import dialogs

    view, ctrl, music, letras, _ = app
    path = str(music / "a.m4a")
    ctrl.auto_sync_lyrics(path)
    ctrl.auto_sync.finished.emit(path, result(0.9))
    song = ctrl.model.song(path)
    assert song.lyrics_backup_path in song.related_paths()
    save_lyrics(LyricsResult(LyricsState.SYNCED, LRC), song.lyrics_base)  # outra letra escolhida
    assert not song.lyrics_backup_path.exists()

    ctrl.auto_sync_lyrics(path)
    ctrl.auto_sync.finished.emit(path, result(0.9))
    monkeypatch.setattr(dialogs, "confirm", lambda *a: True)
    ctrl.delete_songs([path])
    assert list(letras.iterdir()) == []


# ------------------------------------------------------ de ponta a ponta
def test_service_end_to_end_with_real_files(qapp, tmp_path):
    import soundfile as sf
    from PySide6.QtCore import QEventLoop, QTimer

    from karaoke.services import AutoSyncService

    times, text = make_lyrics(lines=16)
    audio, real = sing(times, offset=6.0, jitter=0.15)
    vocals = tmp_path / "vocais.flac"
    sf.write(vocals, np.column_stack([audio, audio]), RATE)
    service, got = AutoSyncService(), []
    loop = QEventLoop()
    service.finished.connect(lambda p, r: (got.append(r), loop.quit()))
    service.failed.connect(lambda p, m: (got.append(m), loop.quit()))
    service.run(tmp_path / "a.m4a", vocals, parse_lrc(text))
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    (r,) = got
    assert r.ok and abs(r.offset - 6.0) < 1.0
    assert np.mean(np.abs(np.array(r.new_times) - np.array(real))) < 0.1
