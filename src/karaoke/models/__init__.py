"""Modelos: dados do aplicativo e seu estado, sem nada de interface."""

from karaoke.models.library_model import MusicLibraryModel
from karaoke.models.lyrics import LyricsState, is_synced_lrc
from karaoke.models.song import Song, SongState
from karaoke.models.song_lists import SongListModel, pending_songs, processed_songs

__all__ = [
    "LyricsState",
    "MusicLibraryModel",
    "Song",
    "SongListModel",
    "SongState",
    "is_synced_lrc",
    "pending_songs",
    "processed_songs",
]
