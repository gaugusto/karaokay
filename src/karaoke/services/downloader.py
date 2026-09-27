"""Download do áudio de vídeos do YouTube com o yt-dlp."""

from __future__ import annotations

import threading
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from PySide6.QtCore import QObject, Signal

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


class DownloadService(QObject):
    """Baixa somente o áudio, na melhor qualidade disponível, um por vez.

    O download roda numa thread de fundo (daemon); os sinais chegam à
    interface pela fila de eventos do Qt.
    """

    progress = Signal(float)   # 0–100
    status = Signal(str)
    finished = Signal(str)     # caminho do arquivo baixado
    failed = Signal(str)       # mensagem de erro

    def __init__(self, output_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._output_dir = output_dir
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def start(self, url: str) -> bool:
        """Inicia o download; retorna False se já houver um em andamento."""
        if self._busy:
            return False
        self._busy = True
        threading.Thread(target=self._run, args=(url.strip(),), name="download", daemon=True).start()
        return True

    def _hook(self, data: dict) -> None:
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            done = data.get("downloaded_bytes") or 0
            if total:
                self.progress.emit(done * 100.0 / total)
        elif data.get("status") == "finished":
            self.progress.emit(100.0)

    def _run(self, url: str) -> None:
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
                info = ydl.extract_info(url, download=False)
                self.status.emit(f"Baixando: {info.get('title') or url}")
                info = ydl.process_ie_result(info, download=True)
                path = info.get("filepath") or ydl.prepare_filename(info)
        except Exception as exc:  # yt-dlp levanta vários tipos de erro
            self._busy = False
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return
        self._busy = False
        self.finished.emit(str(path))
