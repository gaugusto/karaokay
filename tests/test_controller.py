from pathlib import Path

from conftest import add_song, add_stems
from PySide6.QtCore import QObject, Signal

from karaoke.controllers import AppController
from karaoke.models import LyricsState, MusicLibraryModel, SongState
from karaoke.views import MainWindow


class FakeDownloader(QObject):
    progress = Signal(float)
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.urls = []

    def start(self, url):
        self.urls.append(url)
        return True


class FakeSeparator(QObject):
    started = Signal(str)
    progress = Signal(str, int)
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.jobs = []

    def enqueue(self, path, target_dir):
        self.jobs.append((str(path), target_dir))

    def discard(self, path):
        self.discarded = getattr(self, "discarded", []) + [str(path)]


class FakeLyrics(QObject):
    started = Signal(str)
    finished = Signal(str, object, str)
    failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.jobs = []

    def enqueue(self, audio, metadata_path, lyrics_base, priority=False):
        self.jobs.append((str(audio), metadata_path, lyrics_base))
        self.priorities = getattr(self, "priorities", []) + [priority]


def make(dirs):
    music, separated = dirs
    view = MainWindow()
    ctrl = AppController(
        view,
        model=MusicLibraryModel(music, separated),
        downloader=FakeDownloader(),
        separator=FakeSeparator(),
        lyrics=FakeLyrics(),
    )
    return view, ctrl


def titles(proxy):
    return [s.title for s in proxy.songs()]


def test_startup_queues_by_arrival_order(qapp, dirs):
    music, separated = dirs
    add_song(music, "feita.m4a", mtime=1)
    add_song(music, "b.m4a", mtime=30)
    add_song(music, "a.m4a", mtime=20)
    add_song(music, "c.m4a", mtime=10)
    add_stems(separated, "feita")
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    assert [Path(j[0]).stem for j in ctrl.separator.jobs] == ["c", "a", "b"]
    assert ctrl.separator.jobs[0][1] == separated / "c"
    assert titles(ctrl.pending) == ["c", "a", "b"]
    assert titles(ctrl.processed) == ["feita"]
    assert view.pending_panel.header.text() == "A processar (3)"
    assert view.processed_panel.header.text() == "Processadas (1)"


def test_rejects_non_youtube_url(qapp, dirs):
    view, ctrl = make(dirs)
    view.url_submitted.emit("https://exemplo.com/video")
    assert ctrl.downloader.urls == []
    assert "YouTube" in view.statusBar().currentMessage()


def test_new_download_goes_to_end_of_queue(qapp, dirs):
    music, _ = dirs
    add_song(music, "antiga.m4a", mtime=10)
    view, ctrl = make(dirs)
    ctrl.refresh_library()

    view.url_submitted.emit("https://youtu.be/abc")
    assert ctrl.downloader.urls == ["https://youtu.be/abc"]
    assert not view.url_bar.isEnabled()

    song = add_song(music, "Canção [abc].webm")  # mtime atual: chegou por último
    ctrl.downloader.finished.emit(str(song))
    assert view.url_bar.isEnabled()
    assert titles(ctrl.pending) == ["antiga", "Canção [abc]"]
    assert view.pending_panel.view.currentIndex().data() == "Canção [abc]"
    assert len(ctrl.separator.jobs) == 2  # não duplica mesmo com o watcher


def test_processed_song_moves_between_lists(qapp, dirs):
    music, _ = dirs
    a = add_song(music, "a.m4a", mtime=10)
    b = add_song(music, "b.m4a", mtime=20)
    view, ctrl = make(dirs)
    ctrl.refresh_library()

    ctrl.separator.started.emit(str(a))
    assert ctrl.model.song(a).state is SongState.SEPARATING
    assert titles(ctrl.pending) == ["a", "b"]

    ctrl.separator.finished.emit(str(a))
    assert titles(ctrl.pending) == ["b"]
    assert titles(ctrl.processed) == ["a"]
    assert view.pending_panel.header.text() == "A processar (1)"
    assert view.processed_panel.header.text() == "Processadas (1)"

    ctrl.separator.started.emit(str(b))
    ctrl.separator.finished.emit(str(b))
    assert titles(ctrl.pending) == []
    assert titles(ctrl.processed) == ["a", "b"]


def test_failed_song_stays_pending_and_is_not_retried_until_restart(qapp, dirs):
    music, _ = dirs
    a = add_song(music, "a.m4a", mtime=10)
    add_song(music, "b.m4a", mtime=20)
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    ctrl.separator.started.emit(str(a))
    ctrl.separator.failed.emit(str(a), "sem memória")
    assert ctrl.model.song(a).state is SongState.FAILED
    assert titles(ctrl.pending) == ["b", "a"]  # falha vai para o fim
    ctrl.refresh_library()
    assert len(ctrl.separator.jobs) == 2


def test_lyrics_fetched_after_processing(qapp, dirs):
    music, separated = dirs
    a = add_song(music, "a.m4a", mtime=10)
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    assert ctrl.lyrics.jobs == []  # ainda não processada

    ctrl.separator.started.emit(str(a))
    ctrl.separator.finished.emit(str(a))
    assert len(ctrl.lyrics.jobs) == 1
    audio, metadata, base = ctrl.lyrics.jobs[0]
    assert audio == str(a)
    assert base == music.parent / "letras" / "a"
    assert metadata == music / ".metadados" / "a.json"
    assert ctrl.model.song(a).lyrics_state is LyricsState.SEARCHING

    ctrl.lyrics.finished.emit(str(a), LyricsState.SYNCED, "Artista - A")
    assert ctrl.model.song(a).lyrics_state is LyricsState.SYNCED
    assert "sincronizada" in view.statusBar().currentMessage()


def test_startup_fetches_lyrics_only_for_processed_without_lyrics(qapp, dirs):
    music, separated = dirs
    add_song(music, "com.m4a", mtime=1)
    sem = add_song(music, "sem.m4a", mtime=2)
    add_song(music, "nova.m4a", mtime=3)
    add_stems(separated, "com")
    add_stems(separated, "sem")
    letras = music.parent / "letras"
    letras.mkdir()
    (letras / "com.lrc").write_text("[00:01.00] a\n[00:02.00] b\n[00:03.00] c\n")
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    assert [j[0] for j in ctrl.lyrics.jobs] == [str(sem)]
    assert ctrl.model.song(music / "com.m4a").lyrics_state is LyricsState.SYNCED

    ctrl.lyrics.finished.emit(str(sem), LyricsState.NOT_FOUND, "")
    ctrl.refresh_library()  # não repete a busca na mesma sessão
    assert len(ctrl.lyrics.jobs) == 1


def test_progress_shown_while_processing(qapp, dirs):
    from karaoke.views.song_delegate import pending_badge, queue_position

    music, _ = dirs
    a = add_song(music, "a.m4a", mtime=10)
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    ctrl.separator.started.emit(str(a))
    ctrl.separator.progress.emit(str(a), 42)
    song = ctrl.model.song(a)
    assert song.progress == 42
    assert pending_badge(song)[0] == "processando 42%"
    assert queue_position(song, ctrl.pending.index_of(a).row()) == 1

    ctrl.separator.finished.emit(str(a))
    assert ctrl.model.song(a).progress is None
