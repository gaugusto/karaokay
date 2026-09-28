"""Visões: widgets que só exibem dados e emitem sinais, sem regras."""

from karaoke.views.lyrics_search_page import LyricsSearchPage
from karaoke.views.main_window import MainWindow
from karaoke.views.player_window import PlayerWindow
from karaoke.views.youtube_results_page import YouTubeResultsPage
from karaoke.views.song_delegate import PendingSongDelegate, ProcessedSongDelegate

__all__ = ["LyricsSearchPage", "MainWindow", "PendingSongDelegate", "PlayerWindow", "ProcessedSongDelegate", "YouTubeResultsPage"]
