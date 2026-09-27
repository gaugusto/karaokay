"""Controlador do player: liga o StemPlayer, a letra e a janela."""

from __future__ import annotations

import re

from PySide6.QtCore import QObject, Signal

from karaoke.models import Song, load_lyrics, write_lrc_offset
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
        # Começa com os volumes que a janela mostra (voz em 30%)
        self.player.set_vocal_volume(self.view.vocal_volume.volume)
        self.player.set_instrumental_volume(self.view.instrumental_volume.volume)
        self.view.sync_mode_toggled.connect(self._on_sync_mode_toggled)
        self.view.sync_line_clicked.connect(self._on_sync_line_clicked)
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

    @property
    def is_playing(self) -> bool:
        return self.player.state is PlayerState.PLAYING

    def close(self) -> None:
        """Fecha o player sem perguntar (a confirmação, quando existe, já
        aconteceu na janela ou em quem pediu o fechamento)."""
        if self._closing:
            return
        self._closing = True
        self.player.stop()
        self.view.close_without_asking()
        self.view.deleteLater()
        self.closed.emit()

    # --------------------------------------------------------------- sinais
    def _on_loaded(self, duration: float) -> None:
        self.view.set_loading(False)
        self.view.set_duration(duration)  # pronto para tocar; o play fica com o usuário

    def _on_load_failed(self, message: str) -> None:
        self.view.set_loading(False)
        self.view.show_error(message)

    def _on_position(self, seconds: float) -> None:
        self.view.set_position(seconds)
        if not self.view.in_sync_mode:
            self.view.highlight_line(self.lyrics.line_at(seconds))

    # -------------------------------------------------- sincronização manual
    def _on_sync_mode_toggled(self, active: bool) -> None:
        if active and not self.lyrics.synced:
            self.view.set_sync_mode(False)
            return
        self.view.set_sync_mode(active, self.lyrics.first_sung_line())
        if not active:
            self._on_position(self.player.position())

    def _on_sync_line_clicked(self, index: int) -> None:
        """O usuário clicou no primeiro verso no instante em que ele começou:
        desloca a letra inteira para esse verso cair nesse instante."""
        first = self.lyrics.first_sung_line()
        if index != first:
            self.view.show_notice("Clique no primeiro verso (marcado com ▶)", 3000)
            return
        path = self.song.lyrics_path
        if path is None:
            return
        shift = self.player.position() - self.lyrics.lines[first].time
        try:
            write_lrc_offset(path, self.lyrics.offset - shift)
        except OSError as exc:
            self.view.set_sync_mode(False)
            self.view.show_notice(f"Não foi possível salvar o ajuste: {exc}", 6000)
            return
        self.lyrics = load_lyrics(path)
        self.view.set_sync_mode(False)
        self.view.set_lyrics(self.lyrics)
        self._on_position(self.player.position())
        direction = "atrasada" if shift > 0 else "adiantada"
        self.view.show_notice(f"Letra sincronizada: {direction} em {abs(shift):.2f} s".replace(".", ","))

    def _on_state(self, state: PlayerState) -> None:
        self.view.set_playing(state is PlayerState.PLAYING)
