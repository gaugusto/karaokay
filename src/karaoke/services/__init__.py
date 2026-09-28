"""Serviços: integrações externas (yt-dlp, audio-separator), sem interface."""

from karaoke.services.downloader import DownloadService, is_youtube_url, looks_like_url, normalize_youtube_url
from karaoke.services.files import delete_paths
from karaoke.services.lyrics import LrclibClient, ManualLyricsSearch
from karaoke.services.separator import SeparationService
from karaoke.services.stem_player import PlayerState, StemPlayer
from karaoke.services.youtube_search import VideoResult, YouTubeSearchService

__all__ = [
    "DownloadService",
    "LrclibClient",
    "ManualLyricsSearch",
    "PlayerState",
    "SeparationService",
    "StemPlayer",
    "VideoResult",
    "YouTubeSearchService",
    "delete_paths",
    "is_youtube_url",
    "looks_like_url",
    "normalize_youtube_url",
]
