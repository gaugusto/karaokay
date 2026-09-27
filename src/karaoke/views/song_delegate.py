"""Desenho de cada música na lista."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from karaoke.models import MusicLibraryModel, SongState

STATE_LABELS = {
    SongState.QUEUED: "na fila para separar",
    SongState.SEPARATING: "separando vocais…",
    SongState.FAILED: "falha na separação",
}

STATE_TOOLTIPS = {
    SongState.NOT_SEPARATED: "Vocais ainda não separados",
    SongState.QUEUED: "Na fila para separar os vocais",
    SongState.SEPARATING: "Separando os vocais…",
    SongState.SEPARATED: "Vocais separados",
    SongState.FAILED: "Falha na separação",
}


class SongDelegate(QStyledItemDelegate):
    """Mostra o estado ao lado do nome e deixa em cinza as não separadas."""

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        super().initStyleOption(option, index)
        state = index.data(MusicLibraryModel.StateRole)
        label = STATE_LABELS.get(state)
        if label:
            option.text = f"{option.text}   — {label}"
        if state != SongState.SEPARATED:
            dim = option.palette.color(QPalette.ColorRole.PlaceholderText)
            option.palette.setColor(QPalette.ColorRole.Text, dim)


def song_tooltip(index: QModelIndex) -> str:
    song = index.data(MusicLibraryModel.SongRole)
    if song is None:
        return ""
    text = f"{song.path.name}\n{STATE_TOOLTIPS[song.state]}"
    if song.state == SongState.FAILED and song.error:
        text += f": {song.error}"
    return text
