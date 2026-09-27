"""Busca de letras no LRCLIB (https://lrclib.net)."""

from __future__ import annotations

import itertools
import json
import queue
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import shiboken6
from PySide6.QtCore import QObject, Signal

from karaoke import __version__
from karaoke.models.lyrics import PLAIN_EXT, SYNCED_EXT, LyricsState, is_synced_lrc

API_URL = "https://lrclib.net/api"
USER_AGENT = f"karaokay/{__version__} (https://github.com/gaugusto/karaokay)"

# Diferença máxima de duração entre o áudio e a faixa do LRCLIB. O /api/get
# já usa ±2 s; na busca livre aceitamos um pouco mais (clipes têm introduções).
SEARCH_DURATION_TOLERANCE = 10.0


# ---------------------------------------------------------------- título
_NOISE = re.compile(
    r"""[\(\[\{][^\)\]\}]*(
        official|oficial|video|vídeo|clipe|clip|audio|áudio|lyric|letra|visualizer|
        ao\s+vivo|live|hd|hq|4k|remaster|legendad|tradu
    )[^\)\]\}]*[\)\]\}]""",
    re.IGNORECASE | re.VERBOSE,
)
_FEAT = re.compile(r"\s+(?:feat\.?|ft\.?|part\.?|participação)\s+.*$", re.IGNORECASE)
_YOUTUBE_ID = re.compile(r"\s*\[[\w-]{11}\]$")
_CHANNEL_NOISE = re.compile(r"\s*(?:-\s*topic|vevo|oficial|official|tv)$", re.IGNORECASE)


def clean_title(title: str) -> str:
    """Remove o ID do YouTube e marcações como "(Clipe Oficial)"."""
    title = _YOUTUBE_ID.sub("", title)
    title = _NOISE.sub("", title)
    title = re.sub(r"\s*\|.*$", "", title)  # "Música | Canal"
    title = re.sub(r"\s{2,}", " ", title)
    return title.strip(" -–—_")


def clean_artist(name: str) -> str:
    return _CHANNEL_NOISE.sub("", name.strip()).strip()


def split_artist_track(title: str) -> tuple[str, str] | None:
    """ "Artista - Música" -> (artista, música)."""
    parts = re.split(r"\s+[-–—]\s+", clean_title(title), maxsplit=1)
    if len(parts) == 2 and all(parts):
        return clean_artist(parts[0]), _FEAT.sub("", parts[1]).strip()
    return None


@dataclass(frozen=True)
class TrackInfo:
    """O que se sabe da música para procurar a letra."""

    title: str
    artist: str | None = None   # artista informado pelo YouTube (YouTube Music)
    track: str | None = None    # nome da faixa informado pelo YouTube
    channel: str | None = None
    duration: float | None = None

    def guesses(self) -> list[tuple[str, str]]:
        """Pares (música, artista) para tentar, do mais para o menos confiável."""
        found: list[tuple[str, str]] = []
        if self.track and self.artist:
            found.append((self.track, self.artist.split(",")[0].strip()))
        split = split_artist_track(self.title)
        if split:
            found.append((split[1], split[0]))
        if self.channel:
            found.append((_FEAT.sub("", clean_title(self.title)), clean_artist(self.channel)))
        unique = []
        for track, artist in found:
            if track and artist and (track, artist) not in unique:
                unique.append((track, artist))
        return unique


@dataclass(frozen=True)
class LyricsResult:
    state: LyricsState          # SYNCED, PLAIN, INSTRUMENTAL ou NOT_FOUND
    text: str | None = None
    source: str | None = None   # "Artista - Música" como está no LRCLIB


# ---------------------------------------------------------------- cliente
class LrclibClient:
    def __init__(self, base_url: str = API_URL, timeout: float = 15.0) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def _request(self, endpoint: str, params: dict):
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        request = urllib.request.Request(
            f"{self.base_url}/{endpoint}?{query}", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def get(self, track: str, artist: str, duration: float | None = None) -> dict | None:
        return self._request(
            "get",
            {
                "track_name": track,
                "artist_name": artist,
                "duration": round(duration) if duration else None,
            },
        )

    def search(self, **params: str) -> list[dict]:
        return self._request("search", params) or []


def _has_lyrics(record: dict | None) -> bool:
    return bool(record) and bool(record.get("syncedLyrics") or record.get("plainLyrics"))


def _to_result(record: dict) -> LyricsResult:
    source = f"{record.get('artistName')} - {record.get('trackName')}"
    synced = record.get("syncedLyrics")
    if is_synced_lrc(synced):
        return LyricsResult(LyricsState.SYNCED, synced, source)
    plain = record.get("plainLyrics") or synced
    if plain:
        return LyricsResult(LyricsState.PLAIN, plain, source)
    return LyricsResult(LyricsState.INSTRUMENTAL if record.get("instrumental") else LyricsState.NOT_FOUND)


def result_from_record(record: dict) -> LyricsResult:
    """Converte um resultado do LRCLIB em letra pronta para salvar."""
    return _to_result(record)


def record_kind(record: dict) -> LyricsState:
    """SYNCED, PLAIN, INSTRUMENTAL ou NOT_FOUND (sem letra) para um resultado."""
    if is_synced_lrc(record.get("syncedLyrics")):
        return LyricsState.SYNCED
    if record.get("plainLyrics") or record.get("syncedLyrics"):
        return LyricsState.PLAIN
    return LyricsState.INSTRUMENTAL if record.get("instrumental") else LyricsState.NOT_FOUND


def manual_search(client: LrclibClient, artist: str, track: str) -> list[dict]:
    """Busca livre digitada pelo usuário: combina a busca por campos e por
    texto, sem repetir resultados."""
    artist, track = artist.strip(), track.strip()
    queries = []
    if track:
        queries.append({"track_name": track, **({"artist_name": artist} if artist else {})})
    text = " ".join(filter(None, [artist, track]))
    if text:
        queries.append({"q": text})
    seen, results = set(), []
    for params in queries:
        for record in client.search(**params):
            key = record.get("id") or (record.get("artistName"), record.get("trackName"), record.get("duration"))
            if key not in seen:
                seen.add(key)
                results.append(record)
    return results


def sort_candidates(records: list[dict], duration: float | None) -> list[dict]:
    """Sincronizadas primeiro, depois as sem sincronia; em cada grupo, a
    duração mais próxima do áudio primeiro."""
    order = {LyricsState.SYNCED: 0, LyricsState.PLAIN: 1, LyricsState.INSTRUMENTAL: 2, LyricsState.NOT_FOUND: 3}

    def key(record):
        diff = abs(record["duration"] - duration) if duration and record.get("duration") else 0.0
        return (order[record_kind(record)], diff)

    return sorted(records, key=key)


def choose_best(records: list[dict], duration: float | None) -> dict | None:
    """Prefere letra sincronizada e duração mais próxima; descarta durações
    muito diferentes (provavelmente outra versão da música)."""
    candidates = []
    for record in records:
        if not _has_lyrics(record) and not record.get("instrumental"):
            continue
        diff = 0.0
        if duration and record.get("duration"):
            diff = abs(record["duration"] - duration)
            if diff > SEARCH_DURATION_TOLERANCE:
                continue
        synced = is_synced_lrc(record.get("syncedLyrics"))
        candidates.append((not synced, not _has_lyrics(record), diff, record))
    if not candidates:
        return None
    return min(candidates, key=lambda c: c[:3])[3]


def find_lyrics(client: LrclibClient, info: TrackInfo) -> LyricsResult:
    """Tenta /api/get com cada palpite e depois /api/search."""
    fallback: dict | None = None
    guesses = info.guesses()

    for track, artist in guesses:
        record = client.get(track, artist, info.duration)
        if record and is_synced_lrc(record.get("syncedLyrics")):
            return _to_result(record)
        if record and fallback is None and (_has_lyrics(record) or record.get("instrumental")):
            fallback = record

    searches = [{"track_name": t, "artist_name": a} for t, a in guesses]
    searches.append({"q": " ".join(filter(None, [clean_title(info.title), info.artist]))})
    for params in searches:
        best = choose_best(client.search(**params), info.duration)
        if best and is_synced_lrc(best.get("syncedLyrics")):
            return _to_result(best)
        if best and fallback is None:
            fallback = best

    return _to_result(fallback) if fallback else LyricsResult(LyricsState.NOT_FOUND)


# ---------------------------------------------------------------- auxiliares
def audio_duration(path: Path) -> float | None:
    """Duração do áudio em segundos, lida com o ffprobe."""
    if shutil.which("ffprobe") is None:
        return None
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def load_track_info(audio: Path, metadata_path: Path | None) -> TrackInfo:
    """Metadados salvos no download; sem eles, usa o nome do arquivo."""
    data = {}
    if metadata_path and metadata_path.is_file():
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    return TrackInfo(
        title=data.get("title") or audio.stem,
        artist=data.get("artist"),
        track=data.get("track"),
        channel=data.get("channel"),
        duration=audio_duration(audio) or data.get("duration"),
    )


def save_lyrics(result: LyricsResult, base: Path) -> Path | None:
    """Grava letras/<nome>.lrc (sincronizada) ou .txt; apaga a versão antiga."""
    if result.state not in (LyricsState.SYNCED, LyricsState.PLAIN) or not result.text:
        return None
    base.parent.mkdir(parents=True, exist_ok=True)
    ext = SYNCED_EXT if result.state is LyricsState.SYNCED else PLAIN_EXT
    target = base.with_name(base.name + ext)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(result.text.rstrip() + "\n", encoding="utf-8")
    temp.replace(target)
    for other in (SYNCED_EXT, PLAIN_EXT):
        if other != ext:
            base.with_name(base.name + other).unlink(missing_ok=True)
    return target


# ---------------------------------------------------------------- serviço
class ManualLyricsSearch(QObject):
    """Busca manual em segundo plano; cada busca tem um número, e só a mais
    recente é entregue (resultados atrasados são ignorados)."""

    finished = Signal(int, object)  # número da busca, lista de resultados
    failed = Signal(int, str)

    def __init__(self, client: LrclibClient | None = None, parent=None) -> None:
        super().__init__(parent)
        self._client = client or LrclibClient()
        self._request = 0

    def search(self, artist: str, track: str) -> int:
        self._request += 1
        request = self._request

        def work() -> None:
            try:
                signal, args = self.finished, (request, manual_search(self._client, artist, track))
            except Exception as exc:
                signal, args = self.failed, (request, str(exc) or exc.__class__.__name__)
            if not shiboken6.isValid(self):
                return  # janela fechada durante a busca
            try:
                signal.emit(*args)
            except RuntimeError:
                pass

        threading.Thread(target=work, name="busca-manual", daemon=True).start()
        return request

    @property
    def latest(self) -> int:
        return self._request


class LyricsService(QObject):
    """Busca as letras numa thread de fundo, uma música por vez, em ordem.

    Pedidos com ``priority=True`` (alguém esperando para abrir o player)
    passam na frente dos demais.
    """

    started = Signal(str)                   # caminho da música
    finished = Signal(str, object, str)     # caminho, LyricsState, origem ("Artista - Música")
    failed = Signal(str, str)               # caminho, mensagem de erro

    def __init__(self, client: LrclibClient | None = None, parent=None) -> None:
        super().__init__(parent)
        self._client = client or LrclibClient()
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._order = itertools.count()  # desempate: ordem de chegada
        threading.Thread(target=self._loop, name="letras", daemon=True).start()

    def enqueue(
        self,
        audio: str | Path,
        metadata_path: Path | None,
        lyrics_base: Path,
        priority: bool = False,
    ) -> None:
        job = (Path(audio), metadata_path, lyrics_base)
        self._queue.put((0 if priority else 1, next(self._order), job))

    def _loop(self) -> None:
        while True:
            _priority, _order, job = self._queue.get()
            self._fetch(*job)

    def _fetch(self, audio: Path, metadata_path: Path | None, lyrics_base: Path) -> None:
        if not audio.exists():
            return  # música apagada antes da busca
        self.started.emit(str(audio))
        try:
            result = find_lyrics(self._client, load_track_info(audio, metadata_path))
            if not audio.exists():
                return  # apagada durante a busca: não deixa letra órfã
            save_lyrics(result, lyrics_base)
        except Exception as exc:
            self.failed.emit(str(audio), str(exc) or exc.__class__.__name__)
            return
        self.finished.emit(str(audio), result.state, result.source or "")
