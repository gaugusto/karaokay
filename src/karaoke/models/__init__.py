"""Modelos: dados do aplicativo e seu estado, sem nada de interface."""

from karaoke.models.library_model import MusicLibraryModel
from karaoke.models.song import Song, SongState

__all__ = ["MusicLibraryModel", "Song", "SongState"]
