"""Serviços: integrações externas (yt-dlp, audio-separator, MVSEP), sem interface."""

from karaoke.services.downloader import DownloadService, is_youtube_url, looks_like_url, normalize_youtube_url
from karaoke.services.files import delete_paths
from karaoke.services.lyrics import LrclibClient, ManualLyricsSearch
from karaoke.services.mvsep import MvsepSeparationService
from karaoke.services.separator import SeparationService
from karaoke.services.stem_player import PlayerState, StemPlayer
from karaoke.services.youtube_search import VideoResult, YouTubeSearchService

__all__ = [
    "DownloadService",
    "LrclibClient",
    "ManualLyricsSearch",
    "MvsepSeparationService",
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
