"""Modelo Qt com as músicas da pasta e o estado de separação de cada uma."""

from __future__ import annotations

import bisect
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, Qt

from karaoke.models.lyrics import LyricsState
from karaoke.models.song import Song, SongState
from karaoke.paths import AUDIO_EXTENSIONS

_Index = QModelIndex | QPersistentModelIndex


def _sort_key(path: Path) -> str:
    return path.stem.casefold()


class MusicLibraryModel(QAbstractListModel):
    """Lista ordenada das músicas de ``music_dir``.

    ``scan()`` sincroniza com o disco preservando o estado das músicas que já
    estavam na lista; as visões recebem só as linhas inseridas/removidas.
    """

    SongRole = Qt.ItemDataRole.UserRole + 1
    StateRole = Qt.ItemDataRole.UserRole + 2
    PathRole = Qt.ItemDataRole.UserRole + 3

    def __init__(
        self,
        music_dir: Path,
        separated_dir: Path,
        lyrics_dir: Path | None = None,
        metadata_dir: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.music_dir = music_dir
        self.separated_dir = separated_dir
        self.lyrics_dir = lyrics_dir or music_dir.parent / "letras"
        self.metadata_dir = metadata_dir or music_dir / ".metadados"
        self._songs: list[Song] = []

    # ------------------------------------------------------- interface Qt
    def rowCount(self, parent: _Index = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._songs)

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._songs):
            return None
        song = self._songs[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return song.title
        if role == Qt.ItemDataRole.ToolTipRole:
            return song.path.name
        if role == self.SongRole:
            return song
        if role == self.StateRole:
            return song.state
        if role == self.PathRole:
            return str(song.path)
        return None

    # -------------------------------------------------------------- consulta
    def songs(self) -> list[Song]:
        return list(self._songs)

    def song(self, path: str | Path) -> Song | None:
        row = self._row_of(Path(path))
        return None if row is None else self._songs[row]

    def index_of(self, path: str | Path) -> QModelIndex:
        row = self._row_of(Path(path))
        return QModelIndex() if row is None else self.index(row)

    def songs_in_state(self, *states: SongState) -> list[Song]:
        return [s for s in self._songs if s.state in states]

    # ------------------------------------------------------------- alteração
    def scan(self) -> None:
        """Relê a pasta de músicas e atualiza a lista."""
        self.music_dir.mkdir(parents=True, exist_ok=True)
        on_disk = {
            p
            for p in self.music_dir.iterdir()
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        }

        # Remove as que sumiram (de trás para frente para não deslocar índices)
        for row in reversed(range(len(self._songs))):
            if self._songs[row].path not in on_disk:
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._songs[row]
                self.endRemoveRows()

        # Insere as novas na posição ordenada
        known = {s.path for s in self._songs}
        keys = [_sort_key(s.path) for s in self._songs]
        for path in sorted(on_disk - known, key=_sort_key):
            row = bisect.bisect_right(keys, _sort_key(path))
            song = Song(
                path=path,
                stems_dir=self.separated_dir / path.stem,
                lyrics_base=self.lyrics_dir / path.stem,
                metadata_path=self.metadata_dir / f"{path.stem}.json",
                added_at=path.stat().st_mtime,
            )
            self.beginInsertRows(QModelIndex(), row, row)
            self._songs.insert(row, song)
            keys.insert(row, _sort_key(path))
            self.endInsertRows()

        # Músicas paradas refletem o que está no disco
        for song in self._songs:
            if song.state in (SongState.NOT_SEPARATED, SongState.SEPARATED):
                disk_state = (
                    SongState.SEPARATED if song.has_stems_on_disk() else SongState.NOT_SEPARATED
                )
                self.set_state(song.path, disk_state)
            # Letra: o disco manda, exceto durante a busca ou quando já se sabe
            # que não há letra (não encontrada, instrumental, erro)
            if song.lyrics_state in (LyricsState.UNKNOWN, LyricsState.SYNCED, LyricsState.PLAIN):
                self.set_lyrics_state(song.path, song.lyrics_state_on_disk())

    def set_state(self, path: str | Path, state: SongState, error: str | None = None) -> None:
        row = self._row_of(Path(path))
        if row is None:
            return
        song = self._songs[row]
        if song.state == state and song.error == error:
            return
        song.state = state
        song.error = error
        self._changed(row)

    def set_lyrics_state(
        self, path: str | Path, state: LyricsState, error: str | None = None
    ) -> None:
        row = self._row_of(Path(path))
        if row is None:
            return
        song = self._songs[row]
        if song.lyrics_state == state and song.lyrics_error == error:
            return
        song.lyrics_state = state
        song.lyrics_error = error
        self._changed(row)

    def set_progress(self, path: str | Path, percent: int | None) -> None:
        row = self._row_of(Path(path))
        if row is None or self._songs[row].progress == percent:
            return
        self._songs[row].progress = percent
        self._changed(row)

    def set_queue_position(self, path: str | Path, position: int | None) -> None:
        row = self._row_of(Path(path))
        if row is None or self._songs[row].queue_position == position:
            return
        self._songs[row].queue_position = position
        self._changed(row)

    # --------------------------------------------------------------- interno
    def _changed(self, row: int) -> None:
        index = self.index(row)
        # Sem lista de papéis: os proxies refiltram e reordenam em qualquer mudança
        self.dataChanged.emit(index, index, [])

    def _row_of(self, path: Path) -> int | None:
        for row, song in enumerate(self._songs):
            if song.path == path:
                return row
        return None
