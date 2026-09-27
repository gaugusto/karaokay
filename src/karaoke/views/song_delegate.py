"""Desenho de cada música nas listas."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from karaoke.models import MusicLibraryModel, SongState

STATE_LABELS = {
    SongState.NOT_SEPARATED: "aguardando",
    SongState.QUEUED: "aguardando",
    SongState.SEPARATING: "processando…",
    SongState.FAILED: "falha no processamento",
}

STATE_TOOLTIPS = {
    SongState.NOT_SEPARATED: "Aguardando entrar na fila",
    SongState.QUEUED: "Na fila, aguardando a vez",
    SongState.SEPARATING: "Separando vocais e instrumental…",
    SongState.SEPARATED: "Vocais e instrumental separados",
    SongState.FAILED: "Falha no processamento",
}


class PendingSongDelegate(QStyledItemDelegate):
    """Lista a processar: posição na fila, nome e estado.

    A música em processamento aparece em negrito; as que falharam, em cinza.
    """

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        super().initStyleOption(option, index)
        state = index.data(MusicLibraryModel.StateRole)
        prefix = f"{index.row() + 1}.  " if state in (SongState.QUEUED, SongState.SEPARATING) else ""
        option.text = f"{prefix}{option.text}   — {STATE_LABELS.get(state, '')}"
        if state is SongState.SEPARATING:
            font = QFont(option.font)
            font.setBold(True)
            option.font = font
        elif state is SongState.FAILED:
            dim = option.palette.color(QPalette.ColorRole.PlaceholderText)
            option.palette.setColor(QPalette.ColorRole.Text, dim)


def song_tooltip(index: QModelIndex) -> str:
    song = index.data(MusicLibraryModel.SongRole)
    if song is None:
        return ""
    text = f"{song.path.name}\n{STATE_TOOLTIPS[song.state]}"
    if song.state is SongState.FAILED and song.error:
        text += f": {song.error}"
    return text
