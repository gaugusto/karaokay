"""Visões filtradas da biblioteca: músicas a processar e processadas."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSortFilterProxyModel

from karaoke.models.library_model import MusicLibraryModel
from karaoke.models.song import Song, SongState

_Index = QModelIndex | QPersistentModelIndex


class SongListModel(QSortFilterProxyModel):
    """Subconjunto ordenado do MusicLibraryModel.

    Quando o estado de uma música muda, ela entra ou sai desta lista e é
    reposicionada automaticamente (filtro e ordenação dinâmicos).
    """

    def __init__(
        self,
        source: MusicLibraryModel,
        accept: Callable[[Song], bool],
        sort_key: Callable[[Song], Any],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._accept = accept
        self._sort_key = sort_key
        self.setDynamicSortFilter(True)
        self.setSourceModel(source)
        self.sort(0)

    def song_at(self, row: int) -> Song | None:
        return self.index(row, 0).data(MusicLibraryModel.SongRole)

    def songs(self) -> list[Song]:
        return [self.song_at(row) for row in range(self.rowCount())]

    def index_of(self, path) -> QModelIndex:
        return self.mapFromSource(self.sourceModel().index_of(path))

    def filterAcceptsRow(self, source_row: int, source_parent: _Index) -> bool:
        song = self.sourceModel().index(source_row, 0, source_parent).data(MusicLibraryModel.SongRole)
        return song is not None and self._accept(song)

    def lessThan(self, left: _Index, right: _Index) -> bool:
        a = left.data(MusicLibraryModel.SongRole)
        b = right.data(MusicLibraryModel.SongRole)
        return self._sort_key(a) < self._sort_key(b)


def _pending_key(song: Song) -> tuple:
    # Primeiro a que está sendo processada, depois a fila na ordem de entrada;
    # por último as que ainda não entraram na fila (ex.: falhas), por chegada.
    position = song.queue_position if song.queue_position is not None else math.inf
    return (song.state is not SongState.SEPARATING, position, song.added_at, song.title.casefold())


def pending_songs(source: MusicLibraryModel, parent=None) -> SongListModel:
    """Músicas que ainda precisam ser processadas, em ordem de chegada."""
    return SongListModel(source, lambda s: s.state is not SongState.SEPARATED, _pending_key, parent)


def processed_songs(source: MusicLibraryModel, parent=None) -> SongListModel:
    """Músicas já processadas, em ordem alfabética."""
    return SongListModel(
        source, lambda s: s.state is SongState.SEPARATED, lambda s: s.title.casefold(), parent
    )
