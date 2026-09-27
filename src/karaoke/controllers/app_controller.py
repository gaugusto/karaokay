"""Controlador principal: download, fila de processamento e letras."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject

from karaoke import paths
from karaoke.models import (
    LyricsState,
    MusicLibraryModel,
    SongState,
    pending_songs,
    processed_songs,
)
from karaoke.services import DownloadService, LyricsService, SeparationService, is_youtube_url
from karaoke.views import MainWindow


class AppController(QObject):
    def __init__(
        self,
        view: MainWindow,
        model: MusicLibraryModel | None = None,
        downloader: DownloadService | None = None,
        separator: SeparationService | None = None,
        lyrics: LyricsService | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.view = view
        self.model = model or MusicLibraryModel(
            paths.MUSIC_DIR, paths.SEPARATED_DIR, paths.LYRICS_DIR, paths.METADATA_DIR, self
        )
        self.downloader = downloader or DownloadService(paths.MUSIC_DIR, paths.METADATA_DIR, self)
        self.separator = separator or SeparationService(
            paths.MODELS_DIR, paths.SEPARATED_DIR / ".em-andamento", self
        )
        self.lyrics = lyrics or LyricsService(parent=self)

        self.pending = pending_songs(self.model, self)
        self.processed = processed_songs(self.model, self)
        self._next_position = 0

        self.view.set_models(self.pending, self.processed)
        self.view.url_submitted.connect(self.download)

        self.downloader.progress.connect(self.view.set_download_progress)
        self.downloader.status.connect(self.view.show_message)
        self.downloader.finished.connect(self._on_download_finished)
        self.downloader.failed.connect(self._on_download_failed)

        self.separator.started.connect(self._on_separation_started)
        self.separator.progress.connect(self.model.set_progress)
        self.separator.status.connect(self.view.show_message)
        self.separator.finished.connect(self._on_separation_finished)
        self.separator.failed.connect(self._on_separation_failed)

        self.lyrics.started.connect(self._on_lyrics_started)
        self.lyrics.finished.connect(self._on_lyrics_finished)
        self.lyrics.failed.connect(self._on_lyrics_failed)

        self.model.music_dir.mkdir(parents=True, exist_ok=True)
        self._watcher = QFileSystemWatcher([str(self.model.music_dir)], self)
        self._watcher.directoryChanged.connect(self.refresh_library)

    def start(self) -> None:
        self.refresh_library()
        self.view.show()

    # -------------------------------------------------------------- biblioteca
    def refresh_library(self, *_args) -> None:
        """Sincroniza com a pasta e manda para a fila, por ordem de chegada,
        as músicas que ainda não foram processadas."""
        self.model.scan()
        waiting = self.model.songs_in_state(SongState.NOT_SEPARATED)
        for song in sorted(waiting, key=lambda s: (s.added_at, s.title.casefold())):
            self._queue_separation(song.path)
        # Processadas que ainda não têm letra
        for song in self.model.songs_in_state(SongState.SEPARATED):
            self._queue_lyrics(song.path)

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
        self.view.select_pending(self.pending.index_of(path))
        self.view.show_message("Download concluído.", 5000)

    def _on_download_failed(self, message: str) -> None:
        self.view.set_download_running(False)
        self.view.show_message(f"Falha no download: {message}", 10000)

    # --------------------------------------------------------------- separação
    # A fila é FIFO e o SeparationService processa uma música por vez, numa
    # única thread; queue_position registra a ordem de entrada para a visão.
    def _queue_separation(self, path: Path) -> None:
        song = self.model.song(path)
        if song is None or song.state is not SongState.NOT_SEPARATED:
            return
        self._next_position += 1
        self.model.set_queue_position(path, self._next_position)
        self.model.set_state(path, SongState.QUEUED)
        self.separator.enqueue(path, song.stems_dir)

    def _on_separation_started(self, path: str) -> None:
        self.model.set_progress(path, 0)
        self.model.set_state(path, SongState.SEPARATING)

    def _on_separation_finished(self, path: str) -> None:
        self.model.set_progress(path, None)
        self.model.set_queue_position(path, None)
        self.model.set_state(path, SongState.SEPARATED)  # vai para "Processadas"
        self.view.show_message(f"Processada: {Path(path).stem}", 5000)
        self._queue_lyrics(Path(path))

    def _on_separation_failed(self, path: str, message: str) -> None:
        self.model.set_progress(path, None)
        self.model.set_queue_position(path, None)
        self.model.set_state(path, SongState.FAILED, message)
        self.view.show_message(f"Falha ao processar {Path(path).stem}: {message}", 15000)

    # ------------------------------------------------------------------ letras
    # Depois de processada, a música ganha a letra do LRCLIB (em outra fila,
    # para a busca na internet não atrasar a separação da próxima música).
    def _queue_lyrics(self, path: Path) -> None:
        song = self.model.song(path)
        if song is None or song.lyrics_state is not LyricsState.UNKNOWN:
            return
        self.model.set_lyrics_state(path, LyricsState.SEARCHING)
        self.lyrics.enqueue(path, song.metadata_path, song.lyrics_base)

    def _on_lyrics_started(self, path: str) -> None:
        self.model.set_lyrics_state(path, LyricsState.SEARCHING)

    def _on_lyrics_finished(self, path: str, state: LyricsState, source: str) -> None:
        self.model.set_lyrics_state(path, state)
        messages = {
            LyricsState.SYNCED: "letra sincronizada encontrada",
            LyricsState.PLAIN: "letra encontrada, mas sem sincronia",
            LyricsState.INSTRUMENTAL: "música instrumental, sem letra",
            LyricsState.NOT_FOUND: "letra não encontrada no LRCLIB",
        }
        detail = f" ({source})" if source else ""
        self.view.show_message(f"{Path(path).stem}: {messages.get(state, '')}{detail}", 8000)

    def _on_lyrics_failed(self, path: str, message: str) -> None:
        self.model.set_lyrics_state(path, LyricsState.FAILED, message)
        self.view.show_message(f"Erro ao buscar a letra de {Path(path).stem}: {message}", 10000)
