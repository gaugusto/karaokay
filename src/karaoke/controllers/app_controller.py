"""Controlador principal: download, fila de processamento e letras."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QUrl
from PySide6.QtGui import QDesktopServices

from karaoke import paths
from karaoke.models import (
    LyricsState,
    MusicLibraryModel,
    SongState,
    load_lyrics,
    pending_songs,
    processed_songs,
    retime_lrc,
)
from karaoke.services import (
    AutoSyncService,
    DownloadService,
    SeparationService,
    VideoResult,
    YouTubeSearchService,
    delete_paths,
    looks_like_url,
    normalize_youtube_url,
)
from karaoke.services.auto_sync import MAX_SECOND_PEAK
from karaoke.services.auto_sync import MIN_CONFIDENCE as MIN_SYNC_CONFIDENCE
from karaoke.controllers.lyrics_search_controller import LyricsSearchController
from karaoke.controllers.player_controller import PlayerController
from karaoke.views import MainWindow, PlayerWindow, YouTubeResultsPage, dialogs


def _br(value: float) -> str:
    """Número com uma casa decimal e vírgula (ex.: 5,1)."""
    return f"{value:.1f}".replace(".", ",")


class AppController(QObject):
    def __init__(
        self,
        view: MainWindow,
        model: MusicLibraryModel | None = None,
        downloader: DownloadService | None = None,
        separator: SeparationService | None = None,
        auto_sync: AutoSyncService | None = None,
        youtube_search: YouTubeSearchService | None = None,
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

        self.auto_sync = auto_sync or AutoSyncService(self)
        self.youtube_search = youtube_search or YouTubeSearchService(self)
        self.youtube_search.finished.connect(self._on_youtube_results)
        self.youtube_search.failed.connect(self._on_youtube_failed)
        self.youtube_search.thumbnail_ready.connect(self._on_youtube_thumbnail)
        self.results_page: YouTubeResultsPage | None = None
        self._downloads: list[str] = []  # fila de links esperando o download atual
        self._downloading = False
        self._syncing: set[str] = set()

        self.pending = pending_songs(self.model, self)
        self.processed = processed_songs(self.model, self)
        self._next_position = 0

        self.view.set_models(self.pending, self.processed)
        self.view.url_submitted.connect(self.download)
        self.view.play_requested.connect(self.open_player)
        self.view.delete_requested.connect(self.delete_songs)
        self.view.manual_lyrics_requested.connect(self.open_manual_search)
        self.view.auto_sync_requested.connect(self.auto_sync_lyrics)
        self.view.restore_lyrics_requested.connect(self.restore_original_lyrics)
        self.auto_sync.finished.connect(self._on_auto_sync_finished)
        self.auto_sync.failed.connect(self._on_auto_sync_failed)
        self.player: PlayerController | None = None
        self.lyrics_search: LyricsSearchController | None = None
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

        self.model.music_dir.mkdir(parents=True, exist_ok=True)
        self._watcher = QFileSystemWatcher([str(self.model.music_dir)], self)
        self._watcher.directoryChanged.connect(self.refresh_library)

    def start(self) -> None:
        self.refresh_library()
        self.view.show()

    # ------------------------------------------------------------------ player
    def open_player(self, path: str) -> None:
        """Abre o player (dois cliques numa música processada).

        Sem letra baixada, abre antes a busca de letra; o player só abre
        depois que o usuário escolher uma. Nada é baixado automaticamente.
        """
        song = self.model.song(path)
        if song is None or song.state is not SongState.SEPARATED:
            return
        if song.lyrics_path is None:
            self.open_manual_search(path, open_player_after=True)
            return
        self._start_player(song)

    def _start_player(self, song) -> None:
        """O player ocupa a janela principal; ao fechar, as listas voltam."""
        if self.player is not None:
            self.player.close()  # um player por vez
        view = PlayerWindow()
        self.view.show_page(view, song.title)
        self.player = PlayerController(song, view, parent=self)
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
        if self.lyrics_search is not None and self.lyrics_search.song.path in {s.path for s in songs}:
            self.lyrics_search.view.reject()
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
        fecha o player (e as páginas de busca) junto."""
        if self.results_page is not None:
            self.close_youtube_results()
        if self.lyrics_search is not None:
            self.lyrics_search.view.reject()
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
        if sender is not None:
            self.view.show_library(sender.view, self.processed.index_of(sender.song.path))
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

    # ---------------------------------------------------------------- download
    def download(self, text: str) -> None:
        """Barra do topo (ou campo da página de resultados): link do YouTube
        baixa; outro texto pesquisa no YouTube."""
        text = text.strip()
        if not text:
            return
        url = normalize_youtube_url(text)  # aceita também sem https://
        if url is not None:
            self.view.clear_url()
            if self.results_page is not None:
                self.close_youtube_results()  # colou um link na página de resultados
            self._enqueue_download(url)
        elif looks_like_url(text):
            self.view.show_message("Isso não parece um link do YouTube.", 5000)
        else:
            self.search_youtube(text)

    def _enqueue_download(self, url: str) -> None:
        """Um download por vez; os outros esperam na fila, na ordem pedida."""
        if self._downloading or url in self._downloads:
            if url not in self._downloads:
                self._downloads.append(url)
            self.view.show_message(f"Na fila de downloads ({len(self._downloads)} esperando).", 5000)
            return
        if not self.downloader.start(url):  # ocupado por fora do controle da fila
            self._downloads.append(url)
            return
        self._downloading = True
        self.view.set_download_running(True)

    def _start_next_download(self) -> None:
        self._downloading = False
        if self._downloads:
            self._enqueue_download(self._downloads.pop(0))

    def _on_download_finished(self, path: str) -> None:
        self.view.set_download_running(False)
        self.refresh_library()
        self.view.select_pending(self.pending.index_of(path))
        self.view.show_message("Download concluído.", 5000)
        self._start_next_download()

    def _on_download_failed(self, message: str) -> None:
        self.view.set_download_running(False)
        self.view.show_message(f"Falha no download: {message}", 10000)
        self._start_next_download()

    # ------------------------------------------------------- pesquisa no YouTube
    def search_youtube(self, query: str) -> None:
        """Mostra a página de resultados (ocupa a janela, como o player)."""
        page = self.results_page
        if page is None:
            page = self.results_page = YouTubeResultsPage(query)
            page.submitted.connect(self.download)
            page.add_requested.connect(self.add_from_search)
            page.open_requested.connect(self._open_in_browser)
            page.rejected.connect(self.close_youtube_results)
            self.view.show_page(page, "Pesquisar no YouTube")
        self.view.clear_url()
        page.set_searching(query)
        self.youtube_search.search(query)

    def _on_youtube_results(self, request: int, results: list) -> None:
        if self.results_page is not None and request == self.youtube_search.latest:
            self.results_page.set_results(results)

    def _on_youtube_failed(self, request: int, message: str) -> None:
        if self.results_page is not None and request == self.youtube_search.latest:
            self.results_page.show_error(message)

    def _on_youtube_thumbnail(self, request: int, video_id: str, data: bytes) -> None:
        if self.results_page is not None and request == self.youtube_search.latest:
            self.results_page.set_thumbnail(video_id, data)

    def add_from_search(self, result: VideoResult) -> None:
        """"Adicionar": baixa o vídeo escolhido e volta às listas."""
        self.close_youtube_results()
        self._enqueue_download(result.url)
        if self._downloads:
            self.view.show_message(f"Na fila de downloads: {result.title}", 8000)

    def _open_in_browser(self, result: VideoResult) -> None:
        QDesktopServices.openUrl(QUrl(result.url))

    def close_youtube_results(self) -> None:
        page, self.results_page = self.results_page, None
        if page is None:
            return
        self.youtube_search.latest += 1  # respostas atrasadas são ignoradas
        self.view.show_library(page)
        page.deleteLater()
        self.view.focus_url_bar()

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

    def _on_separation_failed(self, path: str, message: str) -> None:
        self.model.set_progress(path, None)
        self.model.set_queue_position(path, None)
        self.model.set_state(path, SongState.FAILED, message)
        self.view.show_message(f"Falha ao processar {Path(path).stem}: {message}", 15000)

    # ------------------------------------------- sincronização automática
    def auto_sync_lyrics(self, path: str) -> None:
        """Alinha a letra (.lrc) com o arquivo de vocais, em segundo plano."""
        song = self.model.song(path)
        if song is None or song.state is not SongState.SEPARATED or path in self._syncing:
            return
        lyrics_path, vocals = song.lyrics_path, song.vocals_path
        if lyrics_path is None or lyrics_path.suffix != ".lrc" or song.lyrics_state is not LyricsState.SYNCED:
            self.view.show_message("Só letras sincronizadas (.lrc) podem ser ajustadas automaticamente.", 8000)
            return
        if vocals is None:
            self.view.show_message("Arquivo de vocais não encontrado.", 8000)
            return
        self._syncing.add(path)
        self.view.show_message(f"Sincronizando a letra de {song.title} com os vocais…")
        self.auto_sync.run(path, vocals, load_lyrics(lyrics_path))

    def _on_auto_sync_finished(self, path: str, result) -> None:
        self._syncing.discard(path)
        song = self.model.song(path)
        if song is None or song.lyrics_path is None:
            return
        percent = f"{result.confidence * 100:.0f}%"
        if not result.ok:
            self.view.show_message(f"Sincronização automática não aplicada ({song.title})", 8000)
            if result.confidence < MIN_SYNC_CONFIDENCE:
                reason = f"confiança {percent}"
            elif result.second_peak > MAX_SECOND_PEAK:  # pico forte, mas não único
                reason = "o alinhamento ficou ambíguo (mais de uma posição parecida)"
            else:  # poucos versos batem com o começo da voz
                reason = (f"só {result.snapped} de {len(result.old_times)} versos "
                          "coincidiram com o começo da voz")
            dialogs.inform(
                self.view,
                "Sincronização automática",
                f"Não foi possível sincronizar \"{song.title}\" com segurança "
                f"({reason}). A letra não foi alterada.\n\n"
                "Talvez a letra seja de outra versão da música: tente outra pela "
                "busca manual, ou ajuste no player com o botão Sincronizar.",
            )
            return
        try:
            backup = song.lyrics_backup_path
            if backup is not None and not backup.exists():
                shutil.copy2(song.lyrics_path, backup)  # guarda a original uma vez
            text = song.lyrics_path.read_text(encoding="utf-8", errors="replace")
            song.lyrics_path.write_text(retime_lrc(text, result.mapping()), encoding="utf-8")
        except OSError as exc:
            self.view.show_message(f"Não foi possível salvar a letra: {exc}", 10000)
            return
        if self.player is not None and self.player.song.path == song.path:
            self.player.reload_lyrics()
        lines = len(result.old_times)
        if result.already_synced:
            summary = (
                f"Letra de {song.title}: já estava praticamente sincronizada; "
                f"{result.snapped} de {lines} versos receberam ajuste fino"
            )
        else:
            sign = "+" if result.offset >= 0 else "−"
            summary = f"Letra de {song.title} sincronizada: deslocamento {sign}{_br(abs(result.offset))} s"
            if abs(result.scale - 1.0) > 1e-6:
                summary += f", andamento {_br(result.scale * 100)}%"
            summary += f", {result.snapped} de {lines} versos com ajuste fino"
        self.view.show_message(f"{summary} (confiança {result.confidence_label}, {percent})", 15000)

    def _on_auto_sync_failed(self, path: str, message: str) -> None:
        self._syncing.discard(path)
        self.view.show_message(f"Erro na sincronização automática: {message}", 10000)

    def restore_original_lyrics(self, path: str) -> None:
        song = self.model.song(path)
        backup = song.lyrics_backup_path if song is not None else None
        if backup is None or not backup.is_file() or song.lyrics_base is None:
            return
        target = song.lyrics_base.with_name(song.lyrics_base.name + ".lrc")
        try:
            shutil.copy2(backup, target)
            backup.unlink()
        except OSError as exc:
            self.view.show_message(f"Não foi possível restaurar a letra: {exc}", 10000)
            return
        self.refresh_library()
        if self.player is not None and self.player.song.path == song.path:
            self.player.reload_lyrics()
        self.view.show_message(f"Letra original de {song.title} restaurada", 8000)

    # ------------------------------------------------------------ letras
    # Letras nunca são baixadas sozinhas: só pela página de busca, quando o
    # usuário escolhe uma (ao abrir o player sem letra, ou pelo botão direito).
    def open_manual_search(self, path: str, open_player_after: bool = False) -> None:
        """Página para procurar a letra digitando artista e música. Com
        ``open_player_after``, o player abre assim que uma letra for escolhida."""
        song = self.model.song(path)
        if song is None or song.state is not SongState.SEPARATED:
            return
        if self.lyrics_search is not None:
            self.lyrics_search.view.reject()  # uma busca por vez
        search = LyricsSearchController(song, parent=self, opening_player=open_player_after)
        search.saved.connect(lambda state: self._on_manual_lyrics_saved(search, state, open_player_after))
        search.cancelled.connect(lambda: self._close_manual_search(search))
        self.lyrics_search = search
        self.view.show_page(search.view, f"Buscar letra — {song.title}")  # ocupa a janela, como o player
        search.start()

    def _on_manual_lyrics_saved(self, search, state, open_player_after: bool) -> None:
        song = search.song
        self._close_manual_search(search)
        self.model.set_lyrics_state(song.path, state)
        kind = "sincronizada" if state is LyricsState.SYNCED else "sem sincronia"
        self.view.show_message(f"Letra {kind} salva para {song.title}", 8000)
        if open_player_after and self.model.song(song.path) is not None:
            self._start_player(song)

    def _close_manual_search(self, search) -> None:
        if self.lyrics_search is search:
            self.lyrics_search = None
        self.view.show_library(search.view, self.processed.index_of(search.song.path))
        search.view.deleteLater()
        search.deleteLater()
