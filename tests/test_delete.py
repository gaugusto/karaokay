import json

import pytest
from conftest import add_song, add_stems
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from karaoke.models import SongState
from karaoke.services import delete_paths


@pytest.fixture
def answers(monkeypatch):
    from karaoke.views import dialogs

    state = {"answer": True, "asked": []}

    def fake_confirm(parent, title, text):
        state["asked"].append((title, text))
        return state["answer"]

    monkeypatch.setattr(dialogs, "confirm", fake_confirm)
    return state


def full_song(music, separated, name):
    """Cria uma música com todos os arquivos relacionados."""
    audio = add_song(music, f"{name}.webm")
    add_stems(separated, name)
    letras = music.parent / "letras"
    letras.mkdir(exist_ok=True)
    (letras / f"{name}.lrc").write_text("[00:01.00]a\n[00:02.00]b\n[00:03.00]c\n")
    meta = music / ".metadados"
    meta.mkdir(exist_ok=True)
    (meta / f"{name}.json").write_text(json.dumps({"title": name}))
    return audio


def all_files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_related_paths_and_delete_only_touch_that_song(qapp, dirs):
    from karaoke.models import MusicLibraryModel

    music, separated = dirs
    full_song(music, separated, "Canção")
    full_song(music, separated, "Canção 2")  # nome parecido: não pode ser apagada
    model = MusicLibraryModel(music, separated)
    model.scan()
    song = model.song(music / "Canção.webm")
    names = sorted(p.name for p in song.related_paths())
    assert names == ["Canção", "Canção.json", "Canção.lrc", "Canção.webm"]

    assert delete_paths(song.related_paths()) == []
    root = music.parent
    assert all_files(root) == [
        "letras/Canção 2.lrc",
        "músicas/.metadados/Canção 2.json",
        "músicas/Canção 2.webm",
        "músicas/separadas/Canção 2/instrumental.flac",
        "músicas/separadas/Canção 2/vocais.flac",
    ]


def make_app(dirs):
    from test_controller import make

    view, ctrl = make(dirs)
    ctrl.refresh_library()
    view.show()
    return view, ctrl


def test_delete_key_asks_and_removes_everything(qapp, dirs, answers):
    music, separated = dirs
    full_song(music, separated, "a")
    full_song(music, separated, "b")
    view, ctrl = make_app(dirs)
    lv = view.processed_panel.view
    lv.setCurrentIndex(ctrl.processed.index_of(music / "a.webm"))

    answers["answer"] = False
    QTest.keyClick(lv, Qt.Key.Key_Delete)
    title, text = answers["asked"][-1]
    assert title == "Excluir música" and '"a"' in text and "não pode ser desfeita" in text
    assert (music / "a.webm").exists()  # cancelou

    answers["answer"] = True
    QTest.keyClick(lv, Qt.Key.Key_Delete)
    assert not (music / "a.webm").exists()
    assert not (separated / "a").exists()
    assert not (music.parent / "letras" / "a.lrc").exists()
    assert not (music / ".metadados" / "a.json").exists()
    assert [s.title for s in ctrl.processed.songs()] == ["b"]
    assert "Excluída: a" in view.statusBar().currentMessage()


def test_delete_several_selected(qapp, dirs, answers):
    music, separated = dirs
    for name in ("a", "b", "c"):
        full_song(music, separated, name)
    view, ctrl = make_app(dirs)
    lv = view.processed_panel.view
    lv.selectionModel().select(ctrl.processed.index_of(music / "a.webm"), lv.selectionModel().SelectionFlag.Select)
    lv.selectionModel().select(ctrl.processed.index_of(music / "c.webm"), lv.selectionModel().SelectionFlag.Select)
    QTest.keyClick(lv, Qt.Key.Key_Delete)
    title, text = answers["asked"][-1]
    assert title == "Excluir músicas" and "Excluir estas 2 músicas?" in text
    assert [s.title for s in ctrl.model.songs()] == ["b"]
    assert "2 músicas excluídas" in view.statusBar().currentMessage()


def test_delete_song_being_processed_discards_result(qapp, dirs, answers):
    music, _ = dirs
    a = add_song(music, "a.m4a", mtime=1)
    b = add_song(music, "b.m4a", mtime=2)
    view, ctrl = make_app(dirs)
    ctrl.separator.started.emit(str(a))
    assert ctrl.model.song(a).state is SongState.SEPARATING

    ctrl.delete_songs([str(a), str(b)])
    assert "interrompido" in answers["asked"][-1][1]
    assert ctrl.separator.discarded == [str(a), str(b)]
    assert ctrl.model.songs() == []


def test_delete_closes_player_of_that_song(qapp, dirs, answers, monkeypatch):
    from test_player import FakePlayer

    from karaoke.controllers import PlayerController
    from karaoke.views import PlayerWindow

    music, separated = dirs
    full_song(music, separated, "a")
    view, ctrl = make_app(dirs)
    monkeypatch.setattr(
        "karaoke.controllers.app_controller.PlayerController",
        lambda song, parent=None: PlayerController(song, PlayerWindow(), FakePlayer(), parent),
    )
    ctrl.open_player(str(music / "a.webm"))
    player_view = ctrl.player.view
    ctrl.delete_songs([str(music / "a.webm")])
    assert "O player será fechado" in answers["asked"][-1][1]
    assert ctrl.player is None and not player_view.isVisible()


def test_delete_reports_files_that_could_not_be_removed(qapp, dirs, answers, monkeypatch):
    import karaoke.controllers.app_controller as app_module

    music, separated = dirs
    full_song(music, separated, "a")
    view, ctrl = make_app(dirs)
    monkeypatch.setattr(app_module, "delete_paths", lambda paths: [(paths[0], "Permissão negada")])
    ctrl.delete_songs([str(music / "a.webm")])
    assert "não puderam ser apagados" in view.statusBar().currentMessage()
    assert "Permissão negada" in view.statusBar().currentMessage()


# ---------------------------------------------------------------- serviços
def test_separation_skips_deleted_and_discards_in_progress(qapp, tmp_path, monkeypatch):
    import sys
    import types

    import karaoke.services.separator as sep_module
    from karaoke.services import SeparationService

    service_ref = {}

    class DeletingSeparator:
        def __init__(self, **kw):
            self.kw = kw

        def load_model(self, model_filename):
            pass

        def separate(self, path, custom_output_names=None):
            from pathlib import Path

            out = Path(self.kw["output_dir"])
            for name in custom_output_names.values():
                (out / f"{name}.flac").write_bytes(b"x")
            service_ref["s"].discard(service_ref["song"])  # apagada no meio

    pkg = types.ModuleType("audio_separator")
    mod = types.ModuleType("audio_separator.separator")
    mod.Separator = DeletingSeparator
    monkeypatch.setitem(sys.modules, "audio_separator", pkg)
    monkeypatch.setitem(sys.modules, "audio_separator.separator", mod)
    monkeypatch.setattr(sep_module, "decode_to_wav", lambda src, dst: dst.write_bytes(b"w"))

    service = SeparationService(tmp_path / "modelos", tmp_path / "trabalho")
    service._hook_progress = lambda: None
    events = []
    service.started.connect(lambda p: events.append("started"))
    service.finished.connect(lambda p: events.append("finished"))

    service._separate(str(tmp_path / "nao-existe.m4a"), tmp_path / "sep" / "x")
    assert events == []  # apagada enquanto esperava: pulada

    song = tmp_path / "a.m4a"
    song.write_bytes(b"x")
    service_ref.update(s=service, song=str(song))
    service._separate(str(song), tmp_path / "sep" / "a")
    assert events == ["started"]  # não publica o resultado
    assert not (tmp_path / "sep" / "a").exists()
    assert not (tmp_path / "trabalho").exists()
