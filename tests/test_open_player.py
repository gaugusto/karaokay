import pytest
from conftest import add_song, add_stems

LRC = "[00:01.00]a\n[00:02.00]b\n[00:03.00]c\n"


@pytest.fixture
def env(qapp, dirs, monkeypatch):
    from test_controller import make

    import karaoke.controllers.app_controller as app_module

    opened, searches = [], []

    class Recorder:
        def __init__(self, song, view=None, parent=None):
            opened.append(song.title)
            self.song = song
            self.closed = type("S", (), {"connect": lambda *a: None})()

        def start(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(app_module, "PlayerController", Recorder)
    monkeypatch.setattr(app_module.AppController, "open_manual_search",
                        lambda self, path, open_player_after=False: searches.append((path, open_player_after)))
    music, separated = dirs
    for name in ("sem", "com"):
        add_song(music, f"{name}.m4a")
        add_stems(separated, name)
    letras = music.parent / "letras"
    letras.mkdir()
    (letras / "com.lrc").write_text(LRC)
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    return {"ctrl": ctrl, "music": music, "opened": opened, "searches": searches}


def test_song_with_lyrics_opens_right_away(env):
    env["ctrl"].open_player(str(env["music"] / "com.m4a"))
    assert env["opened"] == ["com"] and env["searches"] == []


def test_song_without_lyrics_opens_search_window_instead(env):
    path = str(env["music"] / "sem.m4a")
    env["ctrl"].open_player(path)
    assert env["opened"] == []                 # o player espera a escolha da letra
    assert env["searches"] == [(path, True)]   # e abre depois de escolher
