"""Download do áudio de vídeos do YouTube com o yt-dlp."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from PySide6.QtCore import QObject, Signal, Slot

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def is_youtube_url(text: str) -> bool:
    """Retorna True se o texto parece ser um link do YouTube."""
    try:
        parsed = urlparse(text.strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in YOUTUBE_HOSTS


class AudioDownloader(QObject):
    """Baixa somente o áudio, na melhor qualidade disponível.

    Deve ser movido para uma QThread; ``run`` executa o download e emite
    ``progress`` (0–100), depois ``finished`` com o caminho do arquivo ou
    ``failed`` com a mensagem de erro.
    """

    progress = Signal(float)
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, output_dir: Path) -> None:
        super().__init__()
        self._url = url.strip()
        self._output_dir = output_dir

    def _hook(self, data: dict) -> None:
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            done = data.get("downloaded_bytes") or 0
            if total:
                self.progress.emit(done * 100.0 / total)
        elif data.get("status") == "finished":
            self.progress.emit(100.0)

    @Slot()
    def run(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        options = {
            # Melhor faixa só de áudio; sem reconversão, preserva a qualidade original
            "format": "bestaudio/best",
            "outtmpl": str(self._output_dir / "%(title)s [%(id)s].%(ext)s"),
            "noplaylist": True,
            "windowsfilenames": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [self._hook],
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                self.status.emit("Obtendo informações do vídeo…")
                info = ydl.extract_info(self._url, download=False)
                title = info.get("title") or self._url
                self.status.emit(f"Baixando: {title}")
                info = ydl.process_ie_result(info, download=True)
                path = info.get("filepath") or ydl.prepare_filename(info)
        except Exception as exc:  # yt-dlp levanta vários tipos de erro
            self.failed.emit(str(exc))
            return
        self.finished.emit(str(path))
