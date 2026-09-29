"""Separação de vocais na nuvem, pela API do MVSEP (https://mvsep.com/pt/full_api).

Fluxo: envia o áudio (``separation/create``), consulta o andamento
(``separation/get``) até ficar pronto e baixa os arquivos de vocais e
instrumental. Tudo numa thread de fundo, uma música por vez: usuários sem
plano premium só podem ter um trabalho de cada vez no MVSEP.
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from karaoke import __version__
from karaoke.models.song import INSTRUMENTAL_NAME, VOCALS_NAME

API_URL = "https://mvsep.com/api"
USER_AGENT = f"karaokay/{__version__} (https://github.com/gaugusto/karaokay)"

# BS Roformer (vocais, instrumental), modelo ver. 2025.07 — o padrão do MVSEP
# (SDR vocais 11,89 / instrumental 18,20)
SEP_TYPE = 40
MODEL = 81
OUTPUT_FORMAT = 2  # FLAC 16 bits (sem perdas)

# Formatos enviados como estão; os outros (.webm, .opus…) viram FLAC antes
UPLOAD_AS_IS = {".mp3", ".m4a", ".flac", ".wav"}

POLL_INTERVAL = 5.0          # segundos entre as consultas de andamento
MAX_WAIT = 3 * 60 * 60       # desiste depois de 3 horas
MAX_NETWORK_ERRORS = 12      # falhas de rede seguidas toleradas na consulta
TIMEOUT = 60                 # segundos por requisição


class MvsepError(RuntimeError):
    pass


def pick_stems(files: list[dict]) -> tuple[dict, dict]:
    """Entre os arquivos do resultado, (vocais, instrumental).

    O MVSEP nomeia os arquivos como "Vocals"/"Instrumental" (ou dentro do nome
    do arquivo baixado); a comparação ignora maiúsculas.
    """
    vocals = instrumental = None
    for item in files:
        text = " ".join(
            str(item.get(key) or "") for key in ("type", "name", "download_url", "url")
        ).casefold()
        if "instrum" in text:
            instrumental = instrumental or item
        elif "vocal" in text:
            vocals = vocals or item
    if vocals is None or instrumental is None:
        names = ", ".join(str(f.get("name") or f.get("type") or "?") for f in files) or "nada"
        raise MvsepError(f"o MVSEP não devolveu vocais e instrumental (devolveu: {names})")
    return vocals, instrumental


def _file_url(item: dict) -> str:
    url = item.get("download_url") or item.get("url") or item.get("link")
    if not url:
        raise MvsepError("o MVSEP não informou o link de um dos arquivos")
    return str(url)


def _extension(url: str) -> str:
    suffix = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).suffix.lower()
    return suffix if suffix and len(suffix) <= 5 else ".flac"


def encode_to_flac(source: Path, target: Path) -> None:
    """Converte o áudio para FLAC (sem perdas) para enviar ao MVSEP."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg não encontrado; instale com: sudo pacman -S ffmpeg")
    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-vn", "-c:a", "flac", str(target),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1:] or ["erro desconhecido"]
        raise RuntimeError(f"ffmpeg não conseguiu ler o áudio: {detail[0]}")


class _MultipartBody:
    """Corpo multipart/form-data lido aos poucos (o arquivo não vai todo para
    a memória), avisando quantos bytes já foram enviados."""

    def __init__(self, fields: dict[str, str], file_field: str, file_path: Path, on_progress) -> None:
        self.boundary = f"karaokay-{uuid.uuid4().hex}"
        head = b""
        for name, value in fields.items():
            head += (
                f"--{self.boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
            ).encode()
        filename = file_path.name.replace('"', "'")
        head += (
            f"--{self.boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        self._parts = [head, file_path, f"\r\n--{self.boundary}--\r\n".encode()]
        self._size = len(head) + file_path.stat().st_size + len(self._parts[2])
        self._sent = 0
        self._on_progress = on_progress
        self._index = 0
        self._offset = 0
        self._file = None

    @property
    def content_type(self) -> str:
        return f"multipart/form-data; boundary={self.boundary}"

    def __len__(self) -> int:
        return self._size

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self._size
        out = b""
        while len(out) < size and self._index < len(self._parts):
            part = self._parts[self._index]
            if isinstance(part, Path):
                if self._file is None:
                    self._file = part.open("rb")
                chunk = self._file.read(size - len(out))
                if not chunk:
                    self._file.close()
                    self._file = None
                    self._index += 1
                    continue
            else:
                chunk = part[self._offset:self._offset + size - len(out)]
                self._offset += len(chunk)
                if self._offset >= len(part):
                    self._index += 1
                    self._offset = 0
            out += chunk
        self._sent += len(out)
        if self._on_progress and self._size:
            self._on_progress(self._sent / self._size)
        return out

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


class MvsepClient:
    """Chamadas HTTP à API do MVSEP (sem nada de Qt; fácil de trocar nos testes)."""

    def __init__(self, token: str, base_url: str = API_URL, timeout: float = TIMEOUT) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _open(self, request: urllib.request.Request) -> dict:
        request.add_header("User-Agent", USER_AGENT)
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            message = self._message(raw)
            if exc.code == 401:
                raise MvsepError("chave de API do MVSEP inválida") from exc
            raise MvsepError(message or f"o MVSEP respondeu com erro {exc.code}") from exc
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise MvsepError("resposta inesperada do MVSEP") from exc

    @staticmethod
    def _message(raw: bytes) -> str | None:
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, dict) and inner.get("message"):
                return str(inner["message"])
            if data.get("message"):
                return str(data["message"])
            errors = data.get("errors")
            if errors:
                return str(errors)
        return None

    def create(self, audio: Path, on_progress=None) -> str:
        """Envia o áudio e devolve o hash do trabalho."""
        fields = {
            "api_token": self.token,
            "sep_type": str(SEP_TYPE),
            "add_opt1": str(MODEL),
            "output_format": str(OUTPUT_FORMAT),
        }
        body = _MultipartBody(fields, "audiofile", audio, on_progress)
        request = urllib.request.Request(
            f"{self.base_url}/separation/create",
            data=body,
            method="POST",
            headers={"Content-Type": body.content_type, "Content-Length": str(len(body))},
        )
        try:
            data = self._open(request)
        finally:
            body.close()
        inner = data.get("data") if isinstance(data, dict) else None
        if not data.get("success") or not isinstance(inner, dict) or not inner.get("hash"):
            raise MvsepError(self._message(json.dumps(data).encode()) or "o MVSEP recusou o envio")
        return str(inner["hash"])

    def get(self, job: str) -> dict:
        query = urllib.parse.urlencode({"hash": job, "api_token": self.token})
        return self._open(urllib.request.Request(f"{self.base_url}/separation/get?{query}"))

    def cancel(self, job: str) -> None:
        data = urllib.parse.urlencode({"api_token": self.token, "hash": job}).encode()
        try:
            self._open(urllib.request.Request(f"{self.base_url}/separation/cancel", data=data, method="POST"))
        except (MvsepError, OSError):
            pass  # cancelar é só cortesia

    def download(self, url: str, target: Path, on_progress=None) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        partial = target.with_name(target.name + ".part")
        with urllib.request.urlopen(request, timeout=self.timeout) as response, partial.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while chunk := response.read(256 * 1024):
                out.write(chunk)
                done += len(chunk)
                if on_progress and total:
                    on_progress(min(done / total, 1.0))
        partial.replace(target)


class MvsepSeparationService(QObject):
    """Fila de separação pelo MVSEP; mesma interface do SeparationService.

    ``token_provider`` devolve a chave de API na hora de cada trabalho (assim
    uma chave digitada depois já vale para as músicas da fila).
    """

    started = Signal(str)
    progress = Signal(str, int)
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str, str)

    def __init__(
        self,
        work_dir: Path,
        token_provider: Callable[[], str | None],
        client_factory: Callable[[str], MvsepClient] = MvsepClient,
        poll_interval: float = POLL_INTERVAL,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._work_dir = work_dir
        self._token_provider = token_provider
        self._client_factory = client_factory
        self._poll_interval = poll_interval
        self._current: str | None = None
        self._last_percent = -1
        self._discarded: set[str] = set()
        self._queue: queue.Queue[tuple[str, Path]] = queue.Queue()
        threading.Thread(target=self._loop, name="separacao-mvsep", daemon=True).start()

    def enqueue(self, song_path: str | Path, target_dir: Path) -> None:
        self._discarded.discard(str(song_path))
        self._queue.put((str(song_path), target_dir))

    def discard(self, song_path: str | Path) -> None:
        self._discarded.add(str(song_path))

    # --------------------------------------------------------------- interno
    def _loop(self) -> None:
        while True:
            self._separate(*self._queue.get())

    # Faixas da porcentagem: envio 0–30, processamento 30–85, download 85–99
    def _report(self, percent: int) -> None:
        if self._current and percent != self._last_percent:
            self._last_percent = percent
            self.progress.emit(self._current, percent)

    def _is_discarded(self, song_path: str) -> bool:
        return song_path in self._discarded

    def _separate(self, song_path: str, target_dir: Path) -> None:
        if song_path in self._discarded or not Path(song_path).exists():
            self._discarded.discard(song_path)
            return
        self._current = song_path
        self._last_percent = -1
        self.started.emit(song_path)
        self._report(0)
        name = Path(song_path).stem
        try:
            token = (self._token_provider() or "").strip()
            if not token:
                raise MvsepError("chave de API do MVSEP não configurada")
            client = self._client_factory(token)

            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir.mkdir(parents=True)
            source = Path(song_path)
            if source.suffix.lower() not in UPLOAD_AS_IS:
                self.status.emit(f"MVSEP: preparando o áudio de {name}")
                converted = self._work_dir / "_entrada.flac"
                encode_to_flac(source, converted)
                source = converted

            self.status.emit(f"MVSEP: enviando {name}")
            job = client.create(source, lambda f: self._report(int(f * 30)))
            if source.parent == self._work_dir:
                source.unlink(missing_ok=True)
            self._report(30)

            files = self._wait(client, job, song_path, name)
            if files is None:  # música apagada durante o processamento
                return self._drop()

            vocals, instrumental = pick_stems(files)
            self.status.emit(f"MVSEP: baixando vocais e instrumental de {name}")
            for i, (item, stem) in enumerate(((vocals, VOCALS_NAME), (instrumental, INSTRUMENTAL_NAME))):
                url = _file_url(item)
                client.download(
                    url, self._work_dir / f"{stem}{_extension(url)}",
                    lambda f, i=i: self._report(85 + int((i + f) * 7)),
                )

            if self._is_discarded(song_path):
                return self._drop()
            shutil.rmtree(target_dir, ignore_errors=True)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            self._work_dir.rename(target_dir)
        except Exception as exc:
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._current = None
            self.failed.emit(song_path, f"MVSEP: {exc}" if str(exc) else exc.__class__.__name__)
            return
        self._report(100)
        self._current = None
        self.finished.emit(song_path)

    def _drop(self) -> None:
        if self._current:
            self._discarded.discard(self._current)
        shutil.rmtree(self._work_dir, ignore_errors=True)
        self._current = None

    def _wait(self, client: MvsepClient, job: str, song_path: str, name: str) -> list[dict] | None:
        """Consulta o andamento até ficar pronto; devolve a lista de arquivos
        (ou None se a música foi apagada enquanto isso)."""
        start = time.monotonic()
        processing_since: float | None = None
        errors = 0
        while True:
            if self._is_discarded(song_path):
                client.cancel(job)
                return None
            if time.monotonic() - start > MAX_WAIT:
                client.cancel(job)
                raise MvsepError("o processamento demorou demais")
            try:
                answer = client.get(job)
                errors = 0
            except MvsepError:
                raise
            except OSError as exc:  # rede instável: tenta de novo
                errors += 1
                if errors >= MAX_NETWORK_ERRORS:
                    raise MvsepError(f"sem conexão com o MVSEP ({exc})") from exc
                time.sleep(self._poll_interval)
                continue

            status = str(answer.get("status") or "")
            data = answer.get("data") if isinstance(answer.get("data"), dict) else {}
            if not status and answer.get("success") is False:
                raise MvsepError(str(data.get("message") or "o MVSEP recusou a consulta"))
            if status == "done":
                return list(data.get("files") or [])
            if status == "failed":
                raise MvsepError(str(data.get("message") or "o processamento falhou"))
            if status == "not_found":
                raise MvsepError("o trabalho não foi encontrado no MVSEP")
            if status in ("waiting", "distributing") and processing_since is None:
                order, total = data.get("current_order"), data.get("queue_count")
                where = f" (posição {order} de {total})" if order and total else ""
                self.status.emit(f"MVSEP: {name} na fila{where}")
            else:
                if processing_since is None:
                    processing_since = time.monotonic()
                    self.status.emit(f"MVSEP: processando {name}")
                # O MVSEP não informa a porcentagem; avança devagar até 85
                elapsed = time.monotonic() - processing_since
                self._report(30 + int(55 * elapsed / (elapsed + 60)))
            time.sleep(self._poll_interval)
