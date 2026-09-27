from conftest import add_song, add_stems

from karaoke.models import MusicLibraryModel, SongState


def titles(model):
    return [s.title for s in model.songs()]


def test_scan_lists_only_audio_sorted(qapp, dirs):
    music, separated = dirs
    add_song(music, "b.webm")
    add_song(music, "A.m4a")
    add_song(music, "notas.txt")
    add_song(music, "c.webm.part")
    model = MusicLibraryModel(music, separated)
    model.scan()
    assert titles(model) == ["A", "b"]
    assert model.rowCount() == 2


def test_scan_detects_separated_songs(qapp, dirs):
    music, separated = dirs
    add_song(music, "feita.m4a")
    add_song(music, "nova.m4a")
    add_stems(separated, "feita")
    model = MusicLibraryModel(music, separated)
    model.scan()
    assert model.song(music / "feita.m4a").state is SongState.SEPARATED
    assert model.song(music / "nova.m4a").state is SongState.NOT_SEPARATED


def test_scan_keeps_state_and_updates_rows(qapp, dirs):
    music, separated = dirs
    add_song(music, "a.m4a")
    b = add_song(music, "b.m4a")
    model = MusicLibraryModel(music, separated)
    model.scan()
    model.set_state(b, SongState.SEPARATING)

    inserted, removed = [], []
    model.rowsInserted.connect(lambda _p, first, _l: inserted.append(first))
    model.rowsRemoved.connect(lambda _p, first, _l: removed.append(first))

    (music / "a.m4a").unlink()
    add_song(music, "c.m4a")
    model.scan()

    assert titles(model) == ["b", "c"]
    assert model.song(b).state is SongState.SEPARATING  # estado preservado
    assert removed == [0] and inserted == [1]           # sem reset da lista


def test_set_state_emits_data_changed(qapp, dirs):
    music, separated = dirs
    a = add_song(music, "a.m4a")
    model = MusicLibraryModel(music, separated)
    model.scan()
    changed = []
    model.dataChanged.connect(lambda top, _b, _r: changed.append(top.row()))
    model.set_state(a, SongState.FAILED, "erro")
    assert changed == [0]
    assert model.data(model.index(0), MusicLibraryModel.StateRole) is SongState.FAILED
    assert model.song(a).error == "erro"
