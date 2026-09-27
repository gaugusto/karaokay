"""Controlador principal: fluxo de download e separação de vocais."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject

from karaoke import paths
from karaoke.models import MusicLibraryModel, SongState
from karaoke.services import DownloadService, SeparationService, is_youtube_url
from karaoke.views import MainWindow


class AppController(QObject):
    def __init__(
        self,
        view: MainWindow,
        model: MusicLibraryModel | None = None,
        downloader: DownloadService | None = None,
        separator: SeparationService | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.view = view
        self.model = model or MusicLibraryModel(paths.MUSIC_DIR, paths.SEPARATED_DIR, self)
        self.downloader = downloader or DownloadService(paths.MUSIC_DIR, self)
        self.separator = separator or SeparationService(
            paths.MODELS_DIR, paths.SEPARATED_DIR / ".em-andamento", self
        )

        self.view.set_model(self.model)
        self.view.url_submitted.connect(self.download)

        self.downloader.progress.connect(self.view.set_download_progress)
        self.downloader.status.connect(self.view.show_message)
        self.downloader.finished.connect(self._on_download_finished)
        self.downloader.failed.connect(self._on_download_failed)

        self.separator.started.connect(self._on_separation_started)
        self.separator.status.connect(self.view.show_message)
        self.separator.finished.connect(self._on_separation_finished)
        self.separator.failed.connect(self._on_separation_failed)

        self.model.music_dir.mkdir(parents=True, exist_ok=True)
        self._watcher = QFileSystemWatcher([str(self.model.music_dir)], self)
        self._watcher.directoryChanged.connect(self.refresh_library)

    def start(self) -> None:
        self.refresh_library()
        self.view.show()

    # -------------------------------------------------------------- biblioteca
    def refresh_library(self, *_args) -> None:
        """Sincroniza com a pasta e manda para a fila o que falta separar."""
        self.model.scan()
        for song in self.model.songs_in_state(SongState.NOT_SEPARATED):
            self._queue_separation(song.path)

    # ---------------------------------------------------------------- download
    def download(self, url: str) -> None:
        if not is_youtube_url(url):
            self.view.show_message("Isso não parece um link do YouTube.", 5000)
            return
        if not self.downloader.start(url):
            self.view.show_message("Aguarde o download atual terminar.", 5000)
            return
        self.view.set_download_running(True)

    def _on_download_finished(self, path: str) -> None:
        self.view.set_download_running(False)
        self.view.clear_url()
        self.refresh_library()
        self.view.select(self.model.index_of(path))
        self.view.show_message("Download concluído.", 5000)

    def _on_download_failed(self, message: str) -> None:
        self.view.set_download_running(False)
        self.view.show_message(f"Falha no download: {message}", 10000)

    # --------------------------------------------------------------- separação
    def _queue_separation(self, path: Path) -> None:
        song = self.model.song(path)
        if song is None or song.state is not SongState.NOT_SEPARATED:
            return
        self.model.set_state(path, SongState.QUEUED)
        self.separator.enqueue(path, song.stems_dir)
        self._update_separation_count()

    def _on_separation_started(self, path: str) -> None:
        self.model.set_state(path, SongState.SEPARATING)

    def _on_separation_finished(self, path: str) -> None:
        self.model.set_state(path, SongState.SEPARATED)
        self._update_separation_count()
        self.view.show_message(f"Vocais separados: {Path(path).stem}", 5000)

    def _on_separation_failed(self, path: str, message: str) -> None:
        self.model.set_state(path, SongState.FAILED, message)
        self._update_separation_count()
        self.view.show_message(f"Falha ao separar {Path(path).stem}: {message}", 15000)

    def _update_separation_count(self) -> None:
        busy = self.model.songs_in_state(SongState.QUEUED, SongState.SEPARATING)
        self.view.set_separation_count(len(busy))
