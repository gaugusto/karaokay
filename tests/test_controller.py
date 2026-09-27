from conftest import add_song, add_stems
from PySide6.QtCore import QObject, Signal

from karaoke.controllers import AppController
from karaoke.models import MusicLibraryModel, SongState
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
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.jobs = []

    def enqueue(self, path, target_dir):
        self.jobs.append((str(path), target_dir))


def make(dirs):
    music, separated = dirs
    view = MainWindow()
    ctrl = AppController(
        view,
        model=MusicLibraryModel(music, separated),
        downloader=FakeDownloader(),
        separator=FakeSeparator(),
    )
    return view, ctrl


def test_startup_queues_only_unseparated(qapp, dirs):
    music, separated = dirs
    add_song(music, "feita.m4a")
    nova = add_song(music, "nova.m4a")
    add_stems(separated, "feita")
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    assert [j[0] for j in ctrl.separator.jobs] == [str(nova)]
    assert ctrl.separator.jobs[0][1] == separated / "nova"
    assert ctrl.model.song(nova).state is SongState.QUEUED
    assert view.separation_label.text() == "Separando 1 música"


def test_rejects_non_youtube_url(qapp, dirs):
    view, ctrl = make(dirs)
    view.url_submitted.emit("https://exemplo.com/video")
    assert ctrl.downloader.urls == []
    assert "YouTube" in view.statusBar().currentMessage()


def test_download_then_separation_flow(qapp, dirs):
    music, _ = dirs
    view, ctrl = make(dirs)
    view.url_submitted.emit("https://youtu.be/abc")
    assert ctrl.downloader.urls == ["https://youtu.be/abc"]
    assert not view.url_bar.isEnabled()

    song = add_song(music, "Canção [abc].webm")
    ctrl.downloader.finished.emit(str(song))
    assert view.url_bar.isEnabled()
    assert view.song_list.currentIndex().data() == "Canção [abc]"
    assert len(ctrl.separator.jobs) == 1  # não duplica mesmo com o watcher

    ctrl.separator.started.emit(str(song))
    assert ctrl.model.song(song).state is SongState.SEPARATING
    ctrl.separator.finished.emit(str(song))
    assert ctrl.model.song(song).state is SongState.SEPARATED
    assert not view.separation_label.isVisible()


def test_failed_separation_is_not_retried_until_restart(qapp, dirs):
    music, _ = dirs
    song = add_song(music, "a.m4a")
    view, ctrl = make(dirs)
    ctrl.refresh_library()
    ctrl.separator.failed.emit(str(song), "sem memória")
    assert ctrl.model.song(song).state is SongState.FAILED
    ctrl.refresh_library()
    assert len(ctrl.separator.jobs) == 1
