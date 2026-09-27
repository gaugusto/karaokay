"""Serviços: integrações externas (yt-dlp, audio-separator), sem interface."""

from karaoke.services.downloader import DownloadService, is_youtube_url, normalize_youtube_url
from karaoke.services.files import delete_paths
from karaoke.services.lyrics import LrclibClient, ManualLyricsSearch
from karaoke.services.separator import SeparationService
from karaoke.services.stem_player import PlayerState, StemPlayer

__all__ = [
    "DownloadService",
    "LrclibClient",
    "ManualLyricsSearch",
    "PlayerState",
    "SeparationService",
    "StemPlayer",
    "delete_paths",
    "is_youtube_url",
    "normalize_youtube_url",
]
