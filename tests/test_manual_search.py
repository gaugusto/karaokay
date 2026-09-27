import json

import pytest
from conftest import add_song, add_stems
from PySide6.QtCore import QObject, Signal

from karaoke.controllers import LyricsSearchController
from karaoke.models import LyricsState, MusicLibraryModel
from karaoke.services import lyrics as L
from karaoke.views import LyricsSearchDialog

SYNCED = "[00:01.00]um\n[00:02.00]dois\n[00:03.00]três\n"


def rec(id, track="Lugar ao Sol", artist="Charlie Brown Jr.", duration=200.0, synced=SYNCED,
        plain="um\ndois\ntrês", instrumental=False, album="Álbum"):
    return {"id": id, "trackName": track, "artistName": artist, "albumName": album,
            "duration": duration, "syncedLyrics": synced, "plainLyrics": plain,
            "instrumental": instrumental}


# ----------------------------------------------------------------- serviço
class Client:
    def __init__(self, results):
        self.results, self.calls = results, []

    def search(self, **params):
        self.calls.append(params)
        return self.results.get(tuple(sorted(params)), [])


def test_manual_search_combines_field_and_text_queries():
    client = Client({
        ("artist_name", "track_name"): [rec(1), rec(2)],
        ("q",): [rec(2), rec(3)],  # 2 repetido
    })
    results = L.manual_search(client, " Charlie Brown Jr. ", "Lugar ao Sol ")
    assert [r["id"] for r in results] == [1, 2, 3]
    assert client.calls == [
        {"track_name": "Lugar ao Sol", "artist_name": "Charlie Brown Jr."},
        {"q": "Charlie Brown Jr. Lugar ao Sol"},
    ]
    client.calls.clear()
    L.manual_search(client, "", "Lugar ao Sol")  # sem artista
    assert client.calls == [{"track_name": "Lugar ao Sol"}, {"q": "Lugar ao Sol"}]


def test_sort_candidates_and_kinds():
    records = [
        rec(1, synced=None, duration=200),              # sem sincronia
        rec(2, duration=260),                           # sincronizada, longe
        rec(3, duration=202),                           # sincronizada, perto
        rec(4, synced=None, plain=None, instrumental=True),
    ]
    ordered = L.sort_candidates(records, 200.0)
    assert [r["id"] for r in ordered] == [3, 2, 1, 4]
    assert [L.record_kind(r) for r in ordered] == [
        LyricsState.SYNCED, LyricsState.SYNCED, LyricsState.PLAIN, LyricsState.INSTRUMENTAL
    ]


# -------------------------------------------------------- janela + controlador
class FakeSearcher(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.requests, self.latest = [], 0

    def search(self, artist, track):
        self.latest += 1
        self.requests.append((artist, track))
        return self.latest


@pytest.fixture
def song(qapp, dirs, monkeypatch):
    monkeypatch.setattr(L, "audio_duration", lambda p: 200.0)
    music, separated = dirs
    name = "Charlie Brown Jr. - Lugar Ao Sol (Clipe Oficial) [abcdefghijk]"
    add_song(music, f"{name}.webm")
    add_stems(separated, name)
    meta = music / ".metadados"
    meta.mkdir()
    (meta / f"{name}.json").write_text(json.dumps({"title": "Charlie Brown Jr. - Lugar Ao Sol (Clipe Oficial)"}))
    model = MusicLibraryModel(music, separated)
    model.scan()
    return model.songs()[0]


def test_dialog_prefilled_searches_and_saves_choice(song):
    view, searcher = LyricsSearchDialog(song.title), FakeSearcher()
    ctrl = LyricsSearchController(song, view, searcher)
    saved = []
    ctrl.saved.connect(saved.append)
    assert (view.artist_edit.text(), view.track_edit.text()) == ("Charlie Brown Jr.", "Lugar Ao Sol")

    ctrl.start()  # já busca com o palpite
    assert searcher.requests == [("Charlie Brown Jr.", "Lugar Ao Sol")]
    assert not view.search_button.isEnabled()

    searcher.finished.emit(1, [rec(1, synced=None), rec(2, duration=203), rec(3, duration=198)])
    assert view.table.rowCount() == 3
    assert view.table.item(0, 3).text() == "3:18  (-2 s)"  # sincronizada mais próxima primeiro
    assert view.table.item(0, 4).text() == "Sincronizada"
    assert view.preview.toPlainText() == SYNCED  # primeira já selecionada
    assert view.use_button.isEnabled()

    view.table.selectRow(1)
    view.use_button.click()
    assert saved == [LyricsState.SYNCED]
    assert song.lyrics_path.name == f"{song.path.stem}.lrc"
    assert song.lyrics_path.read_text() == SYNCED


def test_instrumental_result_cannot_be_used_and_old_results_ignored(song):
    view, searcher = LyricsSearchDialog(song.title), FakeSearcher()
    ctrl = LyricsSearchController(song, view, searcher)
    ctrl.start()
    view.set_query("Outro", "Nome")
    view.search_button.setEnabled(True)
    view.search_button.click()                     # 2ª busca
    searcher.finished.emit(1, [rec(9)])           # resposta atrasada da 1ª: ignorada
    assert view.table.rowCount() == 0
    searcher.finished.emit(2, [rec(4, synced=None, plain=None, instrumental=True)])
    assert view.table.item(0, 4).text() == "Instrumental"
    assert not view.use_button.isEnabled()

    searcher.finished.emit(2, [])
    assert "Nenhum resultado" in view.status_label.text()
    searcher.failed.emit(2, "sem conexão")
    assert "sem conexão" in view.status_label.text()


def test_plain_choice_saved_as_txt(song):
    view, searcher = LyricsSearchDialog(song.title), FakeSearcher()
    ctrl = LyricsSearchController(song, view, searcher)
    saved = []
    ctrl.saved.connect(saved.append)
    ctrl.start()
    searcher.finished.emit(1, [rec(5, synced=None)])
    view.use_button.click()
    assert saved == [LyricsState.PLAIN] and song.lyrics_path.suffix == ".txt"


# ------------------------------------------------------------ integração
def test_context_menu_search_then_player_opens(qapp, dirs, monkeypatch):
    from test_controller import make

    import karaoke.controllers.app_controller as app_module

    monkeypatch.setattr(L, "audio_duration", lambda p: 200.0)
    opened, created = [], []

    class Recorder:
        def __init__(self, song, parent=None):
            opened.append(song.title)
            self.song = song
            self.closed = type("S", (), {"connect": lambda *a: None})()

        def start(self):
            pass

        def close(self):
            pass

    real = app_module.LyricsSearchController

    def make_search(song, parent_widget=None, parent=None, opening_player=False):
        ctrl = real(song, LyricsSearchDialog(song.title), FakeSearcher(), parent=parent,
                    opening_player=opening_player)
        created.append(ctrl)
        return ctrl

    monkeypatch.setattr(app_module, "PlayerController", Recorder)
    monkeypatch.setattr(app_module, "LyricsSearchController", make_search)
    music, separated = dirs
    add_song(music, "Artista - Música.m4a")
    add_stems(separated, "Artista - Música")
    view, app = make(dirs)
    app.refresh_library()
    path = str(music / "Artista - Música.m4a")

    view.manual_lyrics_requested.emit(path)  # botão direito > Buscar letra manualmente…
    search = created[-1]
    search.searcher.finished.emit(1, [rec(7, "Música", "Artista")])
    search.view.use_button.click()
    assert app.model.song(path).lyrics_state is LyricsState.SYNCED
    assert opened == []  # pela lista, só salva a letra
    assert "Letra sincronizada salva" in view.statusBar().currentMessage()

    (music.parent / "letras" / "Artista - Música.lrc").unlink()  # sem letra de novo
    app.refresh_library()
    app.open_player(path)  # tocar música sem letra abre a busca
    search = created[-1]
    assert search.view.use_button.text() == "Usar e abrir o player"
    search.searcher.finished.emit(1, [rec(8, "Música", "Artista", synced=None)])
    search.view.use_button.click()
    assert opened == ["Artista - Música"]
    assert app.model.song(path).lyrics_state is LyricsState.PLAIN
    assert app.lyrics_search is None


def test_background_search_delivers_on_main_thread(qapp):
    from PySide6.QtCore import QEventLoop, QTimer

    searcher = L.ManualLyricsSearch(Client({("q",): [rec(1)], ("track_name",): [rec(2)]}))
    got = []
    loop = QEventLoop()
    searcher.finished.connect(lambda req, records: (got.append((req, [r["id"] for r in records])), loop.quit()))
    request = searcher.search("", "Lugar ao Sol")
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    assert got == [(request, [2, 1])] and searcher.latest == request


def test_dialog_is_resizable_and_remembers_size(qapp):
    from PySide6.QtCore import QSize, Qt

    LyricsSearchDialog._last_size = None
    dialog = LyricsSearchDialog("Música")
    flags = dialog.windowFlags()
    assert flags & Qt.WindowType.Window and flags & Qt.WindowType.WindowMaximizeButtonHint
    assert dialog.isSizeGripEnabled()
    assert dialog.minimumSize() == QSize(560, 420)
    dialog.show()
    dialog.resize(1000, 800)
    dialog.reject()
    again = LyricsSearchDialog("Outra")
    assert again.size() == QSize(1000, 800)
    LyricsSearchDialog._last_size = None


def test_dialog_explains_when_opening_player(song):
    view = LyricsSearchDialog(song.title)
    LyricsSearchController(song, view, FakeSearcher(), opening_player=True)
    assert "ainda não tem letra" in view.context_note.text()
    assert not view.context_note.isHidden()
    assert view.use_button.text() == "Usar e abrir o player"
    other = LyricsSearchDialog(song.title)
    LyricsSearchController(song, other, FakeSearcher())
    assert other.context_note.isHidden() and other.use_button.text() == "Usar esta letra"
