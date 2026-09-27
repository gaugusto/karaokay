"""Visões: widgets que só exibem dados e emitem sinais, sem regras."""

from karaoke.views.main_window import MainWindow
from karaoke.views.player_window import PlayerWindow
from karaoke.views.song_delegate import PendingSongDelegate, ProcessedSongDelegate

__all__ = ["MainWindow", "PendingSongDelegate", "PlayerWindow", "ProcessedSongDelegate"]
