"""Serviços: integrações externas (yt-dlp, audio-separator), sem interface."""

from karaoke.services.downloader import DownloadService, is_youtube_url
from karaoke.services.separator import SeparationService

__all__ = ["DownloadService", "SeparationService", "is_youtube_url"]
