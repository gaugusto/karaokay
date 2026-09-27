"""Controlador do player: liga o StemPlayer, a letra e a janela."""

from __future__ import annotations

import re

from PySide6.QtCore import QObject, Signal

from karaoke.models import Song, load_lyrics
from karaoke.services import PlayerState, StemPlayer
from karaoke.views.player_window import PlayerWindow


class PlayerController(QObject):
    closed = Signal()

    def __init__(
        self,
        song: Song,
        view: PlayerWindow | None = None,
        player: StemPlayer | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.song = song
        self.view = view or PlayerWindow()
        self.player = player or StemPlayer(self)
        self.lyrics = load_lyrics(song.lyrics_path)
        self._closing = False

        self.view.set_title(re.sub(r"\s*\[[\w-]{11}\]$", "", song.title))  # sem o ID do YouTube
        self.view.set_lyrics(self.lyrics)
        self.view.set_loading(True)

        self.view.toggle_requested.connect(self.player.toggle)
        self.view.seek_requested.connect(self.player.seek)
        self.view.seek_relative_requested.connect(
            lambda delta: self.player.seek(self.player.position() + delta)
        )
        self.view.vocal_volume_changed.connect(self.player.set_vocal_volume)
        self.view.instrumental_volume_changed.connect(self.player.set_instrumental_volume)
        self.view.closed.connect(self.close)

        self.player.loaded.connect(self._on_loaded)
        self.player.load_failed.connect(self._on_load_failed)
        self.player.position_changed.connect(self._on_position)
        self.player.state_changed.connect(self._on_state)

    def start(self) -> None:
        self.view.show()
        self.view.raise_()
        self.view.activateWindow()
        vocals, instrumental = self.song.vocals_path, self.song.instrumental_path
        if vocals is None or instrumental is None:
            self._on_load_failed("vocais/instrumental não encontrados")
            return
        self.player.load(vocals, instrumental)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.player.stop()
        self.view.close()
        self.view.deleteLater()
        self.closed.emit()

    # --------------------------------------------------------------- sinais
    def _on_loaded(self, duration: float) -> None:
        self.view.set_loading(False)
        self.view.set_duration(duration)
        self.player.play()

    def _on_load_failed(self, message: str) -> None:
        self.view.set_loading(False)
        self.view.show_error(message)

    def _on_position(self, seconds: float) -> None:
        self.view.set_position(seconds)
        self.view.highlight_line(self.lyrics.line_at(seconds))

    def _on_state(self, state: PlayerState) -> None:
        self.view.set_playing(state is PlayerState.PLAYING)
