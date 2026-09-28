"""Pesquisa de músicas no YouTube (sem baixar nada) com o yt-dlp.

Usa a busca ``ytsearchN:`` em modo "flat": só a lista de resultados (título,
canal, duração), sem abrir cada vídeo, o que leva poucos segundos. As
miniaturas vêm do servidor de imagens do YouTube, uma por resultado.
"""

from __future__ import annotations

import threading
import urllib.request
from dataclasses import dataclass

import shiboken6
import yt_dlp
from PySide6.QtCore import QObject, Signal

MAX_RESULTS = 10
_EXTRA = 5  # pede alguns a mais: canais, playlists e lives são descartados
THUMBNAIL_URL = "https://i.ytimg.com/vi/{id}/mqdefault.jpg"  # 320×180
THUMBNAIL_TIMEOUT = 10  # s


@dataclass(frozen=True)
class VideoResult:
    id: str
    title: str
    channel: str
    duration: float | None  # s

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"

    @property
    def thumbnail_url(self) -> str:
        return THUMBNAIL_URL.format(id=self.id)

    @property
    def duration_text(self) -> str:
        if not self.duration:
            return ""
        total = int(round(self.duration))
        hours, rest = divmod(total, 3600)
        minutes, seconds = divmod(rest, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def parse_entries(entries, limit: int = MAX_RESULTS) -> list[VideoResult]:
    """Converte os resultados do yt-dlp, ficando só com vídeos comuns."""
    results: list[VideoResult] = []
    seen: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        video_id = entry.get("id")
        ie_key = entry.get("ie_key") or "Youtube"
        if not video_id or ie_key != "Youtube" or video_id in seen:
            continue  # canal, playlist ou repetido
        if entry.get("live_status") in ("is_live", "is_upcoming"):
            continue  # transmissão ao vivo não dá para baixar como música
        seen.add(video_id)
        results.append(
            VideoResult(
                id=video_id,
                title=entry.get("title") or video_id,
                channel=entry.get("channel") or entry.get("uploader") or "",
                duration=entry.get("duration"),
            )
        )
        if len(results) >= limit:
            break
    return results


def search_youtube(query: str, limit: int = MAX_RESULTS) -> list[VideoResult]:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"ytsearch{limit + _EXTRA}:{query}", download=False)
    return parse_entries((info or {}).get("entries"), limit)


def fetch_thumbnail(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=THUMBNAIL_TIMEOUT) as response:
        return response.read()


class YouTubeSearchService(QObject):
    """Faz a pesquisa e baixa as miniaturas em segundo plano.

    Cada pesquisa recebe um número; resultados de uma pesquisa antiga (o
    usuário pesquisou de novo antes de terminar) são ignorados por quem
    recebe, comparando com ``latest``.
    """

    finished = Signal(int, list)             # pedido, [VideoResult]
    failed = Signal(int, str)                # pedido, mensagem
    thumbnail_ready = Signal(int, str, bytes)  # pedido, id do vídeo, imagem

    def __init__(self, parent=None, search=search_youtube, fetch=fetch_thumbnail) -> None:
        super().__init__(parent)
        self._search = search
        self._fetch = fetch
        self.latest = 0

    def search(self, query: str) -> int:
        self.latest += 1
        request = self.latest
        threading.Thread(
            target=self._run, args=(request, query), name="pesquisa-youtube", daemon=True
        ).start()
        return request

    def _emit(self, signal, *args) -> None:
        if not shiboken6.isValid(self):
            return
        try:
            signal.emit(*args)
        except RuntimeError:
            pass  # serviço destruído no meio do caminho

    def _run(self, request: int, query: str) -> None:
        try:
            results = self._search(query)
        except Exception as exc:  # yt-dlp levanta vários tipos de erro
            message = str(exc).removeprefix("ERROR: ") or exc.__class__.__name__
            self._emit(self.failed, request, message)
            return
        self._emit(self.finished, request, results)
        for result in results:
            if request != self.latest:
                return  # nova pesquisa: não adianta baixar estas miniaturas
            try:
                data = self._fetch(result.thumbnail_url)
            except Exception:
                continue  # sem miniatura, fica o quadro vazio
            self._emit(self.thumbnail_ready, request, result.id, data)
