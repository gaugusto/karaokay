"""Download do áudio de vídeos do YouTube com o yt-dlp."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from PySide6.QtCore import QObject, Signal

from karaoke.models.song import METHOD_KEY

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def normalize_youtube_url(text: str) -> str | None:
    """Devolve o link do YouTube pronto para baixar, ou None se não for um.

    Aceita o link com ou sem ``https://`` (ex.: ``youtu.be/ID`` ou
    ``www.youtube.com/watch?v=ID``); sem esquema, completa com ``https://``.
    Encurtadores de outros sites não são aceitos.
    """
    text = text.strip()
    if not text or any(c.isspace() for c in text):
        return None
    if "://" not in text:
        text = f"https://{text}"
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in YOUTUBE_HOSTS:
        return None
    return text


_URL_LIKE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|www\.|[\w-]+(?:\.[\w-]+)+/)", re.IGNORECASE)


def looks_like_url(text: str) -> bool:
    """True se o texto parece um endereço (``https://…``, ``www.…`` ou
    ``site.com/…``); senão é tratado como pesquisa. "t.a.t.u" ou "AC/DC" são
    pesquisas."""
    text = text.strip()
    return bool(text) and not any(c.isspace() for c in text) and bool(_URL_LIKE.match(text))


def is_youtube_url(text: str) -> bool:
    """Retorna True se o texto é um link do YouTube (com ou sem https://)."""
    return normalize_youtube_url(text) is not None


class DownloadService(QObject):
    """Baixa somente o áudio, na melhor qualidade disponível, um por vez.

    O download roda numa thread de fundo (daemon); os sinais chegam à
    interface pela fila de eventos do Qt.
    """

    progress = Signal(float)   # 0–100
    status = Signal(str)
    finished = Signal(str)     # caminho do arquivo baixado
    failed = Signal(str)       # mensagem de erro

    def __init__(self, output_dir: Path, metadata_dir: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self._output_dir = output_dir
        self._metadata_dir = metadata_dir
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def start(self, url: str, method: str | None = None) -> bool:
        """Inicia o download; retorna False se já houver um em andamento.

        ``method`` (método de processamento escolhido) é guardado nos
        metadados, junto com os dados do vídeo.
        """
        if self._busy:
            return False
        self._busy = True
        threading.Thread(
            target=self._run, args=(url.strip(), method), name="download", daemon=True
        ).start()
        return True

    def _hook(self, data: dict) -> None:
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            done = data.get("downloaded_bytes") or 0
            if total:
                self.progress.emit(done * 100.0 / total)
        elif data.get("status") == "finished":
            self.progress.emit(100.0)

    def _run(self, url: str, method: str | None = None) -> None:
        # Baixa numa subpasta e só move para a biblioteca depois de salvar os
        # metadados: assim, quando a música aparece na pasta (e o app a manda
        # para a fila), o método de processamento escolhido já está gravado.
        temp_dir = self._output_dir / ".baixando"
        temp_dir.mkdir(parents=True, exist_ok=True)
        options = {
            # Melhor faixa só de áudio; sem reconversão, preserva a qualidade original
            "format": "bestaudio/best",
            "outtmpl": str(temp_dir / "%(title)s [%(id)s].%(ext)s"),
            "noplaylist": True,
            # Mantém a data do arquivo como o momento do download (ordem de chegada),
            # em vez da data de publicação do vídeo
            "updatetime": False,
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
                downloaded = Path(info.get("filepath") or ydl.prepare_filename(info))
            path = self._output_dir / downloaded.name
            self._save_metadata(path, info, method)
            downloaded.replace(path)
        except Exception as exc:  # yt-dlp levanta vários tipos de erro
            self._busy = False
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return
        self._busy = False
        self.finished.emit(str(path))

    def _save_metadata(self, audio: Path, info: dict, method: str | None = None) -> None:
        """Guarda os dados do vídeo usados depois para achar a letra e o
        método de processamento escolhido."""
        if self._metadata_dir is None:
            return
        artists = info.get("artists") or ([info["artist"]] if info.get("artist") else [])
        data = {
            "id": info.get("id"),
            "url": info.get("webpage_url"),
            "title": info.get("title"),
            "track": info.get("track"),
            "artist": ", ".join(artists) or None,
            "album": info.get("album"),
            "channel": info.get("channel") or info.get("uploader"),
            "duration": info.get("duration"),
        }
        if method is not None:
            data[METHOD_KEY] = str(getattr(method, "value", method))
        try:
            self._metadata_dir.mkdir(parents=True, exist_ok=True)
            target = self._metadata_dir / f"{audio.stem}.json"
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass  # sem metadados a letra é buscada pelo nome do arquivo
