import threading

import pytest
from conftest import add_song, add_stems

from karaoke.models import LyricsState

LRC = "[00:01.00]a\n[00:02.00]b\n[00:03.00]c\n"


@pytest.fixture
def env(qapp, dirs, monkeypatch):
    """App com o player e os diálogos simulados."""
    from test_controller import make

    import karaoke.controllers.app_controller as app_module
    from karaoke.views import dialogs

    opened, informed = [], []

    class Recorder:
        def __init__(self, song, parent=None):
            opened.append(song.title)
            self.song = song
            self.closed = type("S", (), {"connect": lambda *a: None})()

        def start(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(app_module, "PlayerController", Recorder)
    manual = []
    offer_answer = {"value": False}

    def fake_offer(parent, title, text, action):
        informed.append((title, text))
        return offer_answer["value"]

    monkeypatch.setattr(dialogs, "offer", fake_offer)
    monkeypatch.setattr(app_module.AppController, "open_manual_search",
                        lambda self, path, open_player_after=False: manual.append((path, open_player_after)))

    music, separated = dirs
    add_song(music, "sem.m4a")
    add_stems(separated, "sem")
    add_song(music, "com.m4a")
    add_stems(separated, "com")
    letras = music.parent / "letras"
    letras.mkdir()
    (letras / "com.lrc").write_text(LRC)

    view, ctrl = make(dirs)
    ctrl.refresh_library()
    return {"view": view, "ctrl": ctrl, "music": music, "letras": letras,
            "opened": opened, "informed": informed, "manual": manual, "offer": offer_answer}


def test_song_with_lyrics_opens_right_away(env):
    ctrl = env["ctrl"]
    jobs_before = len(ctrl.lyrics.jobs)
    ctrl.open_player(str(env["music"] / "com.m4a"))
    assert env["opened"] == ["com"]
    assert len(ctrl.lyrics.jobs) == jobs_before  # nada a buscar


def test_missing_lyrics_are_fetched_first_then_player_opens(env):
    ctrl, view, music = env["ctrl"], env["view"], env["music"]
    path = str(music / "sem.m4a")
    ctrl.lyrics.finished.emit(path, LyricsState.NOT_FOUND, "")  # busca automática falhou antes
    jobs_before = len(ctrl.lyrics.jobs)

    ctrl.open_player(path)
    assert env["opened"] == []  # ainda não abre
    assert len(ctrl.lyrics.jobs) == jobs_before + 1  # tenta de novo...
    assert ctrl.lyrics.priorities[-1] is True       # ...passando na frente
    assert ctrl.model.song(path).lyrics_state is LyricsState.SEARCHING
    assert "Buscando a letra de sem" in view.statusBar().currentMessage()

    (env["letras"] / "sem.lrc").write_text(LRC)  # o serviço salvou a letra
    ctrl.lyrics.finished.emit(path, LyricsState.SYNCED, "A - sem")
    assert env["opened"] == ["sem"] and env["informed"] == []


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (("finished", LyricsState.NOT_FOUND), "não foi encontrada no LRCLIB"),
        (("finished", LyricsState.INSTRUMENTAL), "instrumental"),
        (("failed", "sem conexão"), "Erro ao buscar a letra: sem conexão"),
    ],
)
def test_player_not_opened_when_lyrics_cannot_be_fetched(env, outcome, expected):
    ctrl = env["ctrl"]
    path = str(env["music"] / "sem.m4a")
    ctrl.open_player(path)
    kind, value = outcome
    if kind == "finished":
        ctrl.lyrics.finished.emit(path, value, "")
    else:
        ctrl.lyrics.failed.emit(path, value)
    assert env["opened"] == []
    (title, text), = env["informed"]
    assert title == "Letra não encontrada"
    assert '"sem"' in text and expected in text and "não será aberto" in text
    assert env["manual"] == []  # escolheu "Fechar"


def test_not_found_warning_offers_manual_search(env):
    ctrl = env["ctrl"]
    path = str(env["music"] / "sem.m4a")
    env["offer"]["value"] = True  # clicou em "Buscar manualmente…"
    ctrl.open_player(path)
    ctrl.lyrics.finished.emit(path, LyricsState.NOT_FOUND, "")
    assert env["manual"] == [(path, True)]  # abre o player depois de escolher
    assert env["opened"] == []


def test_only_the_awaited_song_opens(env):
    ctrl, music = env["ctrl"], env["music"]
    ctrl.open_player(str(music / "sem.m4a"))
    ctrl.open_player(str(music / "com.m4a"))  # mudou de ideia: abre a outra
    assert env["opened"] == ["com"]
    (env["letras"] / "sem.lrc").write_text(LRC)
    ctrl.lyrics.finished.emit(str(music / "sem.m4a"), LyricsState.SYNCED, "")
    assert env["opened"] == ["com"]  # a busca antiga não abre nada


def test_priority_request_jumps_the_queue(qapp, tmp_path, monkeypatch):
    import karaoke.services.lyrics as L

    monkeypatch.setattr(L, "audio_duration", lambda p: None)
    gate, order = threading.Event(), []

    class Client:
        def get(self, track, artist, duration=None):
            order.append(track)
            if track == "primeira":
                gate.wait(5)  # segura a fila enquanto os outros chegam
            return None

        def search(self, **params):
            return []

    service = L.LyricsService(Client())
    done = threading.Event()
    service.finished.connect(lambda p, s, src: done.set() if "normal2" in p else None)

    def audio(name):
        path = tmp_path / f"Artista - {name}.m4a"
        path.write_bytes(b"x")
        return path

    service.enqueue(audio("primeira"), None, tmp_path / "l" / "1")
    while not order:
        pass
    service.enqueue(audio("normal1"), None, tmp_path / "l" / "2")
    service.enqueue(audio("normal2"), None, tmp_path / "l" / "3")
    service.enqueue(audio("urgente"), None, tmp_path / "l" / "4", priority=True)
    gate.set()

    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(3000, loop.quit)
    service.finished.connect(lambda p, s, src: loop.quit() if "normal2" in p else None)
    loop.exec()
    firsts = [t for i, t in enumerate(order) if t not in order[:i]]  # ordem da 1ª tentativa
    assert firsts == ["primeira", "urgente", "normal1", "normal2"]
