"""Controlador da busca manual de letra."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from karaoke.models import LyricsState, Song
from karaoke.services import ManualLyricsSearch
from karaoke.services.lyrics import (
    clean_title,
    load_track_info,
    record_kind,
    result_from_record,
    save_lyrics,
    sort_candidates,
)
from karaoke.views.lyrics_search_dialog import LyricsSearchDialog


class LyricsSearchController(QObject):
    """Abre a janela, faz as buscas e salva a letra escolhida.

    Emite ``saved`` com o estado da letra gravada (SYNCED ou PLAIN) ou
    ``cancelled`` se a janela for fechada sem escolher.
    """

    saved = Signal(object)  # LyricsState
    cancelled = Signal()

    def __init__(
        self,
        song: Song,
        view: LyricsSearchDialog | None = None,
        searcher: ManualLyricsSearch | None = None,
        parent_widget=None,
        parent=None,
        opening_player: bool = False,
    ) -> None:
        super().__init__(parent)
        self.song = song
        self.view = view or LyricsSearchDialog(song.title, parent_widget)
        self.searcher = searcher or ManualLyricsSearch(parent=self)
        info = load_track_info(song.path, song.metadata_path)
        self.duration = info.duration

        guesses = info.guesses()
        track, artist = guesses[0] if guesses else (clean_title(info.title), info.artist or "")
        self.view.set_query(artist, track)
        self.view.set_reference_duration(self.duration)
        self.view.set_opening_player(opening_player)

        self.view.search_requested.connect(self._search)
        self.searcher.finished.connect(self._on_results)
        self.searcher.failed.connect(self._on_error)
        self.view.accepted.connect(self._on_accepted)
        self.view.rejected.connect(self.cancelled)

    def start(self) -> None:
        """Mostra a janela e já faz a primeira busca com o palpite."""
        self.view.show()
        self.view.raise_()
        self.view.activateWindow()
        self.view.search_button.click()

    def _search(self, artist: str, track: str) -> None:
        self.searcher.search(artist, track)

    def _on_results(self, request: int, records: list) -> None:
        if request != self.searcher.latest:
            return
        records = sort_candidates(records, self.duration)
        self.view.set_results(records, [record_kind(r) for r in records])

    def _on_error(self, request: int, message: str) -> None:
        if request == self.searcher.latest:
            self.view.show_error(message)

    def _on_accepted(self) -> None:
        record = self.view.selected_record()
        if record is None or self.song.lyrics_base is None:
            self.cancelled.emit()
            return
        result = result_from_record(record)
        try:
            save_lyrics(result, self.song.lyrics_base)
        except OSError as exc:
            self.view.show_error(f"não foi possível salvar: {exc}")
            self.cancelled.emit()
            return
        self.saved.emit(result.state if result.state in (LyricsState.SYNCED, LyricsState.PLAIN) else None)
