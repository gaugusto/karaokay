"""Serviços: integrações externas (yt-dlp, audio-separator), sem interface."""

from karaoke.services.downloader import DownloadService, is_youtube_url
from karaoke.services.lyrics import LrclibClient, LyricsService
from karaoke.services.separator import SeparationService

__all__ = ["DownloadService", "LrclibClient", "LyricsService", "SeparationService", "is_youtube_url"]
