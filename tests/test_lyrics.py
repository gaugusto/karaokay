import json

import pytest

from karaoke.models import LyricsState, is_synced_lrc
from karaoke.models.lyrics import lyrics_state_on_disk
from karaoke.services import lyrics as L

SYNCED = "[00:12.34] Primeira linha\n[00:15.00] Segunda\n[00:18.50] Terceira\n"
PLAIN = "Primeira linha\nSegunda\nTerceira\n"


@pytest.mark.parametrize(
    "text, synced",
    [
        (SYNCED, True),
        ("[ar:Artista]\n[ti:Música]\n" + SYNCED, True),  # cabeçalho LRC não atrapalha
        (PLAIN, False),
        ("[00:00.00] a\n[00:00.00] b\n[00:00.00] c\n", False),  # tempos falsos
        ("[00:01.00] só uma linha\n", False),
        ("", False),
        (None, False),
    ],
)
def test_is_synced_lrc(text, synced):
    assert is_synced_lrc(text) is synced


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Lugar Ao Sol [DRhEueqE7Uw]", "Lugar Ao Sol"),
        ("Charlie Brown Jr. - Lugar Ao Sol (Clipe Oficial)", "Charlie Brown Jr. - Lugar Ao Sol"),
        ("Queen – Bohemian Rhapsody (Official Video Remastered)", "Queen – Bohemian Rhapsody"),
        ("Artista - Música [Lyric Video] | Canal", "Artista - Música"),
    ],
)
def test_clean_title(title, expected):
    assert L.clean_title(title) == expected


def test_guesses_order():
    info = L.TrackInfo(
        title="Charlie Brown Jr. - Lugar Ao Sol (Clipe Oficial)",
        artist="Charlie Brown Jr.",
        track="Lugar ao Sol",
        channel="Charlie Brown Jr. - Topic",
    )
    assert info.guesses() == [
        ("Lugar ao Sol", "Charlie Brown Jr."),
        ("Lugar Ao Sol", "Charlie Brown Jr."),
        ("Charlie Brown Jr. - Lugar Ao Sol", "Charlie Brown Jr."),
    ]


def test_guesses_from_filename_and_channel():
    info = L.TrackInfo(title="Lugar Ao Sol [DRhEueqE7Uw]", channel="CharlieBrownJrVEVO")
    assert info.guesses() == [("Lugar Ao Sol", "CharlieBrownJr")]


def rec(track="M", artist="A", duration=200.0, synced=SYNCED, plain=PLAIN, instrumental=False):
    return {
        "trackName": track, "artistName": artist, "duration": duration,
        "syncedLyrics": synced, "plainLyrics": plain, "instrumental": instrumental,
    }


def test_choose_best_prefers_synced_then_duration():
    records = [
        rec(track="sem sync", synced=None),
        rec(track="longe", duration=260.0),
        rec(track="perto", duration=201.0),
        rec(track="exata sem sync", duration=200.0, synced=None),
    ]
    assert L.choose_best(records, 200.0)["trackName"] == "perto"


def test_choose_best_rejects_other_versions():
    assert L.choose_best([rec(duration=320.0)], 200.0) is None


class FakeClient:
    def __init__(self, get=None, search=None):
        self._get = get or {}
        self._search = search or {}
        self.calls = []

    def get(self, track, artist, duration=None):
        self.calls.append(("get", track, artist, duration))
        return self._get.get((track, artist))

    def search(self, **params):
        self.calls.append(("search", params))
        return self._search.get(tuple(sorted(params.items())), [])


def test_find_lyrics_uses_get_first():
    client = FakeClient(get={("Lugar Ao Sol", "Charlie Brown Jr."): rec("Lugar Ao Sol", "Charlie Brown Jr.")})
    info = L.TrackInfo(title="Charlie Brown Jr. - Lugar Ao Sol (Clipe Oficial)", duration=200.0)
    result = L.find_lyrics(client, info)
    assert result.state is LyricsState.SYNCED
    assert result.source == "Charlie Brown Jr. - Lugar Ao Sol"
    assert client.calls == [("get", "Lugar Ao Sol", "Charlie Brown Jr.", 200.0)]


def test_find_lyrics_falls_back_to_search_and_plain():
    q = (("q", "Lugar Ao Sol"),)
    client = FakeClient(search={q: [rec(synced=None, duration=203.0)]})
    result = L.find_lyrics(client, L.TrackInfo(title="Lugar Ao Sol [DRhEueqE7Uw]", duration=200.0))
    assert result.state is LyricsState.PLAIN
    assert result.text == PLAIN


def test_find_lyrics_not_found_and_instrumental():
    assert L.find_lyrics(FakeClient(), L.TrackInfo(title="Nada")).state is LyricsState.NOT_FOUND
    client = FakeClient(get={("Solo", "Banda"): rec(synced=None, plain=None, instrumental=True)})
    info = L.TrackInfo(title="Banda - Solo")
    assert L.find_lyrics(client, info).state is LyricsState.INSTRUMENTAL


def test_save_lyrics_writes_same_name_as_audio(tmp_path):
    base = tmp_path / "letras" / "Lugar Ao Sol [DRhEueqE7Uw]"
    path = L.save_lyrics(L.LyricsResult(LyricsState.PLAIN, PLAIN), base)
    assert path.name == "Lugar Ao Sol [DRhEueqE7Uw].txt"
    path = L.save_lyrics(L.LyricsResult(LyricsState.SYNCED, SYNCED), base)
    assert path.name == "Lugar Ao Sol [DRhEueqE7Uw].lrc"
    assert not base.with_name(base.name + ".txt").exists()  # substitui a sem sincronia
    assert lyrics_state_on_disk(base) == (LyricsState.SYNCED, path)
    assert L.save_lyrics(L.LyricsResult(LyricsState.NOT_FOUND), base) is None


def test_load_track_info_prefers_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "audio_duration", lambda p: 201.5)
    meta = tmp_path / "a.json"
    meta.write_text(json.dumps({"title": "T", "artist": "A", "track": "M", "channel": "C", "duration": 199}))
    info = L.load_track_info(tmp_path / "a [x].webm", meta)
    assert (info.title, info.artist, info.track, info.channel, info.duration) == ("T", "A", "M", "C", 201.5)
    info = L.load_track_info(tmp_path / "Só o Nome [x].webm", tmp_path / "nao-existe.json")
    assert info.title == "Só o Nome [x]" and info.artist is None


def test_service_saves_file_and_reports(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(L, "audio_duration", lambda p: 200.0)
    client = FakeClient(get={("Música", "Artista"): rec("Música", "Artista")})
    service = L.LyricsService(client)
    done = []
    service.finished.connect(lambda path, state, source: done.append((state, source)))
    base = tmp_path / "letras" / "Artista - Música [abcdefghijk]"
    audio = tmp_path / "Artista - Música [abcdefghijk].webm"
    audio.write_bytes(b"x")
    service._fetch(audio, None, base)
    assert done == [(LyricsState.SYNCED, "Artista - Música")]
    assert (tmp_path / "letras" / "Artista - Música [abcdefghijk].lrc").read_text() == SYNCED


def test_client_http_against_local_server():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            seen.append((url.path, parse_qs(url.query), self.headers["User-Agent"]))
            if url.path == "/api/get" and parse_qs(url.query)["track_name"] == ["Existe"]:
                body, code = json.dumps(rec("Existe", "A")), 200
            elif url.path == "/api/search":
                body, code = json.dumps([rec("Busca", "A")]), 200
            else:
                body, code = json.dumps({"code": 404, "name": "TrackNotFound"}), 404
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = L.LrclibClient(f"http://127.0.0.1:{server.server_port}/api")
        assert client.get("Existe", "A", 199.6)["trackName"] == "Existe"
        assert client.get("Não existe", "A") is None  # 404 vira None
        assert client.search(q="lugar ao sol")[0]["trackName"] == "Busca"
    finally:
        server.shutdown()
    path, params, agent = seen[0]
    assert path == "/api/get"
    assert params == {"track_name": ["Existe"], "artist_name": ["A"], "duration": ["200"]}
    assert agent.startswith("karaokay/")
    assert "duration" not in seen[1][1]


def test_downloader_saves_metadata(qapp, tmp_path):
    from karaoke.services import DownloadService

    service = DownloadService(tmp_path, tmp_path / ".metadados")
    info = {
        "id": "abcdefghijk", "title": "Artista - Música (Clipe Oficial)", "track": "Música",
        "artists": ["Artista", "Outro"], "channel": "Artista", "duration": 201,
    }
    service._save_metadata(tmp_path / "Artista - Música (Clipe Oficial) [abcdefghijk].webm", info)
    data = json.loads((tmp_path / ".metadados" / "Artista - Música (Clipe Oficial) [abcdefghijk].json").read_text())
    assert data["artist"] == "Artista, Outro" and data["track"] == "Música" and data["duration"] == 201
