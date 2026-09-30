"""Segundo método de processamento: MVSEP (nuvem)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import add_song
from PySide6.QtWidgets import QApplication
from test_controller import make

from karaoke.models import SeparationMethod, SongState
from karaoke.models.song import METHOD_KEY, read_separation_method
from karaoke.services import mvsep
from karaoke.services.mvsep import MvsepClient, MvsepError, MvsepSeparationService, _MultipartBody, pick_stems
from karaoke.views import settings as prefs


@pytest.fixture(autouse=True)
def clean_prefs(monkeypatch, tmp_path):
    monkeypatch.delenv(prefs.MVSEP_TOKEN_ENV, raising=False)
    monkeypatch.setattr(prefs, "mvsep_token_file", lambda: tmp_path / ".mvsep-token")
    yield
    s = prefs.settings()
    s.remove(prefs.MVSEP_TOKEN_KEY)
    s.remove(prefs.LAST_METHOD_KEY)


def write_method(music: Path, stem: str, method: str) -> None:
    folder = music / ".metadados"
    folder.mkdir(exist_ok=True)
    (folder / f"{stem}.json").write_text(json.dumps({"title": stem, METHOD_KEY: method}))


# ------------------------------------------------------------- controlador
def test_chosen_method_goes_to_downloader_and_to_the_right_queue(qapp, dirs):
    music, separated = dirs
    prefs.set_mvsep_api_token("chave")
    view, ctrl = make(dirs, method=SeparationMethod.MVSEP)
    view.url_submitted.emit("https://youtu.be/abc")
    assert ctrl.downloader.methods == ["mvsep"]
    assert prefs.last_separation_method() == "mvsep"

    write_method(music, "Canção [abc]", "mvsep")
    song = add_song(music, "Canção [abc].webm")
    add_song(music, "manual.mp3")  # colocada à mão: sem metadados, local
    ctrl.downloader.finished.emit(str(song))
    assert ctrl.cloud_separator.jobs == [(str(song), separated / "Canção [abc]")]
    assert [Path(p).name for p, _ in ctrl.separator.jobs] == ["manual.mp3"]

    # os sinais do MVSEP movem a música entre as listas como os da separação local
    ctrl.cloud_separator.started.emit(str(song))
    assert ctrl.model.song(song).state is SongState.SEPARATING
    ctrl.cloud_separator.failed.emit(str(song), "MVSEP: erro")
    assert ctrl.model.song(song).state is SongState.FAILED


def test_cancelling_the_question_downloads_nothing(qapp, dirs):
    view, ctrl = make(dirs, method=None)
    view.url_bar.setText("https://youtu.be/abc")
    view.url_submitted.emit("https://youtu.be/abc")
    assert ctrl.downloader.urls == []
    assert view.url_bar.text() == "https://youtu.be/abc"  # o link continua no campo


def test_last_choice_is_the_default(qapp, dirs):
    prefs.set_last_separation_method("mvsep")
    prefs.set_mvsep_api_token("chave")
    view, ctrl = make(dirs)
    seen = []
    ctrl.choose_method = lambda parent, default: seen.append(default) or default
    view.url_submitted.emit("https://youtu.be/abc")
    assert seen == [SeparationMethod.MVSEP] and ctrl.downloader.methods == ["mvsep"]


def test_mvsep_without_token_asks_for_it(qapp, dirs):
    view, ctrl = make(dirs, method=SeparationMethod.MVSEP)
    ctrl.ask_mvsep_token = lambda parent: None  # cancelou
    view.url_submitted.emit("https://youtu.be/abc")
    assert ctrl.downloader.urls == []

    ctrl.ask_mvsep_token = lambda parent: "nova-chave"
    view.url_submitted.emit("https://youtu.be/abc")
    assert ctrl.downloader.methods == ["mvsep"]
    assert prefs.mvsep_api_token() == "nova-chave"


def test_token_from_env_or_file(monkeypatch, tmp_path):
    assert prefs.mvsep_api_token() is None
    (tmp_path / ".mvsep-token").write_text("do-arquivo\n")
    assert prefs.mvsep_api_token() == "do-arquivo"
    monkeypatch.setenv(prefs.MVSEP_TOKEN_ENV, "do-ambiente")
    assert prefs.mvsep_api_token() == "do-ambiente"


def test_queued_downloads_keep_their_method(qapp, dirs):
    music, _ = dirs
    prefs.set_mvsep_api_token("chave")
    view, ctrl = make(dirs, method=SeparationMethod.MVSEP)
    view.url_submitted.emit("https://youtu.be/a")
    ctrl.choose_method = lambda parent, default: SeparationMethod.LOCAL
    view.url_submitted.emit("https://youtu.be/b")
    assert ctrl.downloader.urls == ["https://youtu.be/a"]
    ctrl.downloader.finished.emit(str(add_song(music, "a.webm")))
    assert ctrl.downloader.urls == ["https://youtu.be/a", "https://youtu.be/b"]
    assert ctrl.downloader.methods == ["mvsep", "local"]


def test_read_separation_method(tmp_path):
    assert read_separation_method(None) is SeparationMethod.LOCAL
    assert read_separation_method(tmp_path / "nao-existe.json") is SeparationMethod.LOCAL
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({METHOD_KEY: "mvsep"}))
    assert read_separation_method(meta) is SeparationMethod.MVSEP
    meta.write_text(json.dumps({METHOD_KEY: "outro"}))
    assert read_separation_method(meta) is SeparationMethod.LOCAL


def test_downloader_moves_file_only_after_saving_method(qapp, tmp_path, monkeypatch):
    """A música só aparece na pasta com o método já gravado nos metadados."""
    from karaoke.services import downloader as dl

    music = tmp_path / "músicas"
    seen_on_arrival = {}

    class FakeYDL:
        def __init__(self, options):
            self.template = options["outtmpl"]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            return {"id": "abc", "title": "Canção", "duration": 100}

        def process_ie_result(self, info, download=True):
            path = Path(self.template.replace("%(title)s", "Canção").replace("%(id)s", "abc").replace("%(ext)s", "webm"))
            assert path.parent != music  # baixa fora da biblioteca
            path.write_bytes(b"audio")
            return {**info, "filepath": str(path)}

    monkeypatch.setattr(dl.yt_dlp, "YoutubeDL", FakeYDL)
    service = dl.DownloadService(music, music / ".metadados")
    service.finished.connect(lambda p: seen_on_arrival.setdefault("path", p))
    service._busy = True
    service._run("https://youtu.be/abc", "mvsep")
    QApplication.processEvents()
    final = music / "Canção [abc].webm"
    assert final.read_bytes() == b"audio"
    assert seen_on_arrival["path"] == str(final)
    meta = json.loads((music / ".metadados" / "Canção [abc].json").read_text())
    assert meta[METHOD_KEY] == "mvsep" and meta["title"] == "Canção"


# ---------------------------------------------------------------- serviço
def test_pick_stems():
    files = [
        {"name": "Instrumental", "download_url": "https://x/b.flac"},
        {"name": "Vocals", "download_url": "https://x/a.flac"},
    ]
    vocals, instrumental = pick_stems(files)
    assert vocals["name"] == "Vocals" and instrumental["name"] == "Instrumental"
    # nomes só no link do arquivo
    vocals, instrumental = pick_stems([
        {"download_url": "https://x/musica_vocals.flac"},
        {"download_url": "https://x/musica_instrum.flac"},
    ])
    assert "vocals" in vocals["download_url"]
    with pytest.raises(MvsepError, match="não devolveu"):
        pick_stems([{"name": "Drums", "download_url": "https://x/d.flac"}])


def test_multipart_body_streams_the_file(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"0123456789" * 1000)
    progress = []
    body = _MultipartBody({"api_token": "t", "sep_type": "40"}, "audiofile", audio, progress.append)
    data = b""
    while chunk := body.read(777):
        data += chunk
    assert len(data) == len(body)
    assert b'name="api_token"\r\n\r\nt\r\n' in data
    assert b'filename="a.mp3"' in data and audio.read_bytes() in data
    assert data.endswith(f"--{body.boundary}--\r\n".encode())
    assert progress[-1] == 1.0


class FakeClient:
    """Cliente falso: fila → processando → pronto."""

    def __init__(self, statuses, files=None):
        self.statuses = list(statuses)
        self.files = files if files is not None else [
            {"name": "Vocals", "download_url": "https://mvsep/r/vocals.flac"},
            {"name": "Instrumental", "download_url": "https://mvsep/r/instrumental.flac"},
        ]
        self.uploaded = None
        self.cancelled = []

    def create(self, audio, on_progress=None):
        self.uploaded = Path(audio).name
        if on_progress:
            on_progress(1.0)
        return "hash1"

    def get(self, job):
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if isinstance(status, dict):
            return status
        data = {"files": self.files} if status == "done" else {"current_order": 2, "queue_count": 5}
        return {"success": True, "status": status, "data": data}

    def cancel(self, job):
        self.cancelled.append(job)

    def download(self, url, target, on_progress=None):
        target.write_bytes(url.encode())


def run_service(tmp_path, client, token="chave", song_name="música.mp3"):
    song = tmp_path / song_name
    song.write_bytes(b"audio")
    target = tmp_path / "separadas" / song.stem
    service = MvsepSeparationService(
        tmp_path / "trabalho", lambda: token, client_factory=lambda t: client, poll_interval=0
    )
    events = []
    service.status.connect(lambda m: events.append(("status", m)))
    service.finished.connect(lambda p: events.append(("finished", p)))
    service.failed.connect(lambda p, m: events.append(("failed", m)))
    service._separate(str(song), target)  # direto, sem a thread
    QApplication.processEvents()
    return song, target, events


def test_service_uploads_waits_and_downloads(qapp, tmp_path):
    client = FakeClient(["waiting", "processing", "done"])
    song, target, events = run_service(tmp_path, client)
    assert client.uploaded == "música.mp3"  # mp3 vai como está
    assert (target / "vocais.flac").read_bytes() == b"https://mvsep/r/vocals.flac"
    assert (target / "instrumental.flac").read_bytes() == b"https://mvsep/r/instrumental.flac"
    assert ("finished", str(song)) in events
    messages = [m for kind, m in events if kind == "status"]
    assert any("na fila (posição 2 de 5)" in m for m in messages)
    assert any("processando" in m for m in messages)
    assert not (tmp_path / "trabalho").exists()


def test_service_converts_webm_before_upload(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(mvsep, "encode_to_flac", lambda src, dst: dst.write_bytes(b"flac"))
    client = FakeClient(["done"])
    run_service(tmp_path, client, song_name="música.webm")
    assert client.uploaded == "_entrada.flac"


def test_service_reports_failure(qapp, tmp_path):
    client = FakeClient([{"success": True, "status": "failed", "data": {"message": "arquivo corrompido"}}])
    _, target, events = run_service(tmp_path, client)
    assert ("failed", "MVSEP: arquivo corrompido") in events
    assert not target.exists()


def test_service_without_token_fails(qapp, tmp_path):
    _, _, events = run_service(tmp_path, FakeClient(["done"]), token="")
    assert ("failed", "MVSEP: chave de API do MVSEP não configurada") in events


def test_deleted_song_cancels_the_job(qapp, tmp_path):
    client = FakeClient(["processing"])
    song = tmp_path / "música.mp3"
    song.write_bytes(b"audio")
    service = MvsepSeparationService(tmp_path / "trabalho", lambda: "t", client_factory=lambda t: client, poll_interval=0.01)
    original_get = client.get

    def get(job):
        service.discard(song)  # apagada enquanto processava
        return original_get(job)

    client.get = get
    events = []
    service.finished.connect(lambda p: events.append("finished"))
    service.failed.connect(lambda p, m: events.append(m))
    service._separate(str(song), tmp_path / "separadas" / "música")
    QApplication.processEvents()
    assert client.cancelled == ["hash1"] and events == []
    assert not (tmp_path / "separadas").exists()


# ------------------------------------------------- cliente HTTP (servidor local)
class _Api(BaseHTTPRequestHandler):
    calls: list = []

    def log_message(self, *args):
        pass

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length)
        _Api.calls.append(("POST", self.path, self.headers["Content-Type"], body))
        if b"chave-ruim" in body:
            return self._json(401, {"success": False, "data": {"message": "Unknown API token"}})
        self._json(200, {"success": True, "data": {"hash": "h123", "link": "x"}})

    def do_GET(self):
        url = urlparse(self.path)
        _Api.calls.append(("GET", url.path, parse_qs(url.query), None))
        if url.path == "/api/separation/get":
            return self._json(200, {"success": True, "status": "done", "data": {"files": []}})
        payload = b"FLACDATA" * 100
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def api():
    _Api.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Api)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_client_talks_to_the_api(api, tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio-bytes")
    client = MvsepClient("minha-chave", base_url=f"{api}/api")

    assert client.create(audio) == "h123"
    method, path, content_type, body = _Api.calls[0]
    assert (method, path) == ("POST", "/api/separation/create")
    assert content_type.startswith("multipart/form-data; boundary=")
    for field, value in (("api_token", "minha-chave"), ("sep_type", "40"), ("add_opt1", "81"), ("output_format", "2")):
        assert f'name="{field}"\r\n\r\n{value}\r\n'.encode() in body
    assert b'name="audiofile"; filename="a.mp3"' in body and b"audio-bytes" in body

    assert client.get("h123")["status"] == "done"
    assert _Api.calls[1][2] == {"hash": ["h123"], "api_token": ["minha-chave"]}

    target = tmp_path / "vocais.flac"
    progress = []
    client.download(f"{api}/files/v.flac", target, progress.append)
    assert target.read_bytes() == b"FLACDATA" * 100 and progress[-1] == 1.0

    with pytest.raises(MvsepError, match="inválida"):
        MvsepClient("chave-ruim", base_url=f"{api}/api").create(audio)


# ------------------------------------------------------------------ diálogo
def test_method_dialog_shows_full_texts_and_returns_choice(qapp):
    from PySide6.QtCore import QTimer

    from karaoke.views import dialogs

    dialog = dialogs.SeparationMethodDialog(None, SeparationMethod.MVSEP)
    dialog.show()
    QApplication.processEvents()
    for method, button in dialog.buttons.items():
        assert button.text().startswith(method.label)
        assert button.sizeHint().width() <= button.width()  # nada cortado
    assert dialog.buttons[SeparationMethod.MVSEP].isDefault()  # Enter repete a última
    dialog.close()

    def click_local():
        shown = next(w for w in QApplication.topLevelWidgets()
                     if isinstance(w, dialogs.SeparationMethodDialog) and w.isVisible())
        shown.buttons[SeparationMethod.LOCAL].click()

    QTimer.singleShot(0, click_local)
    assert dialogs.choose_separation_method(None, SeparationMethod.MVSEP) is SeparationMethod.LOCAL

    def cancel():
        next(w for w in QApplication.topLevelWidgets()
             if isinstance(w, dialogs.SeparationMethodDialog) and w.isVisible()).cancel_button.click()

    QTimer.singleShot(0, cancel)
    assert dialogs.choose_separation_method(None, SeparationMethod.LOCAL) is None
