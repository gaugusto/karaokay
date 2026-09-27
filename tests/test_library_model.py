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


def test_song_lists_split_and_order(qapp, dirs):
    from conftest import add_song as add

    from karaoke.models import pending_songs, processed_songs

    music, separated = dirs
    add(music, "z.m4a", mtime=1)
    b = add(music, "b.m4a", mtime=2)
    add(music, "a.m4a", mtime=3)
    add_stems(separated, "z")
    model = MusicLibraryModel(music, separated)
    model.scan()
    pending, processed = pending_songs(model), processed_songs(model)
    assert [s.title for s in pending.songs()] == ["b", "a"]  # ordem de chegada
    assert [s.title for s in processed.songs()] == ["z"]

    model.set_state(b, SongState.SEPARATED)
    assert [s.title for s in pending.songs()] == ["a"]
    assert [s.title for s in processed.songs()] == ["b", "z"]


def test_scan_reads_lyrics_state(qapp, dirs):
    from karaoke.models import LyricsState

    music, separated = dirs
    add_song(music, "s.m4a")
    add_song(music, "p.m4a")
    add_song(music, "n.m4a")
    letras = music.parent / "letras"
    letras.mkdir()
    (letras / "s.lrc").write_text("[00:01.00] a\n[00:02.00] b\n[00:03.00] c\n")
    (letras / "p.txt").write_text("a\nb\n")
    model = MusicLibraryModel(music, separated)
    model.scan()
    assert model.song(music / "s.m4a").lyrics_state is LyricsState.SYNCED
    assert model.song(music / "p.m4a").lyrics_state is LyricsState.PLAIN
    assert model.song(music / "n.m4a").lyrics_state is LyricsState.UNKNOWN
    assert model.song(music / "s.m4a").lyrics_path == letras / "s.lrc"
