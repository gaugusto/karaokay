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
from karaoke.services import (
    DownloadService,
    LyricsService,
    SeparationService,
    delete_paths,
    is_youtube_url,
)
from karaoke.controllers.player_controller import PlayerController
from karaoke.views import MainWindow, dialogs


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
        self.view.play_requested.connect(self.open_player)
        self.view.delete_requested.connect(self.delete_songs)
        self.player: PlayerController | None = None
        self.view.close_guard = self._can_close

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

    # ------------------------------------------------------------------ player
    def open_player(self, path: str) -> None:
        """Abre o player (dois cliques numa música processada)."""
        song = self.model.song(path)
        if song is None or song.state is not SongState.SEPARATED:
            return
        if self.player is not None:
            self.player.close()  # um player por vez
        self.player = PlayerController(song, parent=self)
        self.player.closed.connect(self._on_player_closed)
        self.player.start()

    # ----------------------------------------------------------------- excluir
    def delete_songs(self, paths: list[str]) -> None:
        """Tecla Delete: confirma e apaga a música e todos os seus arquivos."""
        songs = [s for s in (self.model.song(p) for p in paths) if s is not None]
        if not songs:
            return
        if len(songs) == 1:
            title = "Excluir música"
            question = f"Excluir \"{songs[0].title}\"?"
        else:
            title = "Excluir músicas"
            names = "\n".join(f"• {s.title}" for s in songs[:8])
            more = f"\n… e mais {len(songs) - 8}" if len(songs) > 8 else ""
            question = f"Excluir estas {len(songs)} músicas?\n\n{names}{more}"
        details = (
            "\n\nSerão apagados o áudio, os vocais e o instrumental separados, "
            "a letra e os metadados. Esta ação não pode ser desfeita."
        )
        if any(s.state is SongState.SEPARATING for s in songs):
            details += "\nO processamento em andamento será interrompido."
        if self.player is not None and self.player.song.path in {s.path for s in songs}:
            details += "\nO player será fechado."
        if not dialogs.confirm(self.view, title, question + details):
            return

        if self.player is not None and self.player.song.path in {s.path for s in songs}:
            self.player.close()
        errors = []
        for song in songs:
            if song.state in (SongState.QUEUED, SongState.SEPARATING):
                self.separator.discard(song.path)
            errors += delete_paths(song.related_paths())
        self.refresh_library()

        if errors:
            failed = "; ".join(f"{p.name}: {msg}" for p, msg in errors[:3])
            self.view.show_message(f"Alguns arquivos não puderam ser apagados — {failed}", 15000)
        elif len(songs) == 1:
            self.view.show_message(f"Excluída: {songs[0].title}", 5000)
        else:
            self.view.show_message(f"{len(songs)} músicas excluídas", 5000)

    def _can_close(self) -> bool:
        """Ao fechar a janela principal: confirma se há música tocando e
        fecha o player junto."""
        if self.player is None:
            return True
        if self.player.is_playing and not dialogs.confirm(
            self.view, "Fechar o Karaokê", "Uma música está tocando. Deseja fechar o programa?"
        ):
            return False
        self.player.close()
        return True

    def _on_player_closed(self) -> None:
        sender = self.sender()
        if sender is self.player:
            self.player = None
        if sender is not None:
            sender.deleteLater()

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
