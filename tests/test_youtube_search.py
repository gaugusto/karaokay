"""Pesquisa no YouTube pela barra do topo e página de resultados."""

import pytest
from conftest import add_song
from PySide6.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from karaoke.services import VideoResult, looks_like_url
from karaoke.services.youtube_search import YouTubeSearchService, parse_entries


def entry(id, title=None, channel="Canal", duration=213.0, **extra):
    return {"_type": "url", "ie_key": "Youtube", "id": id, "title": title or f"Vídeo {id}",
            "channel": channel, "duration": duration, **extra}


# ----------------------------------------------------------------- serviço
def test_parse_entries_keeps_only_videos():
    entries = [
        entry("a1"),
        {"_type": "url", "ie_key": "YoutubeTab", "id": "UCcanal", "title": "Um canal"},
        entry("a1"),  # repetido
        entry("live", live_status="is_live"),
        entry("b2", channel=None, uploader="Enviado por"),
        None,
        entry("c3", duration=None),
    ]
    results = parse_entries(entries)
    assert [r.id for r in results] == ["a1", "b2", "c3"]
    assert results[1].channel == "Enviado por"
    assert results[0].url == "https://www.youtube.com/watch?v=a1"
    assert results[0].thumbnail_url == "https://i.ytimg.com/vi/a1/mqdefault.jpg"
    assert parse_entries([entry(str(i)) for i in range(20)], limit=10)[-1].id == "9"


@pytest.mark.parametrize("seconds, text", [(213, "3:33"), (59.6, "1:00"), (3725, "1:02:05"), (None, "")])
def test_duration_text(seconds, text):
    assert VideoResult("x", "t", "c", seconds).duration_text == text


@pytest.mark.parametrize("text, expected", [
    ("https://exemplo.com/video", True),
    ("www.exemplo.com", True),
    ("exemplo.com/video", True),
    ("lugar ao sol", False),
    ("despacito", False),
    ("t.a.t.u", False),
    ("AC/DC", False),
    ("", False),
])
def test_looks_like_url(text, expected):
    assert looks_like_url(text) is expected


def _collect(signal):
    got = []
    signal.connect(lambda *args: got.append(args))
    return got


def _wait_until(condition, timeout=3000):
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: condition() and loop.quit())
    timer.start(10)
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()
    timer.stop()


def test_service_emits_results_then_thumbnails(qapp):
    results = [VideoResult("a", "A", "c", 1), VideoResult("b", "B", "c", 2)]
    service = YouTubeSearchService(search=lambda q: results, fetch=lambda url: url.encode())
    got, thumbs = _collect(service.finished), _collect(service.thumbnail_ready)
    request = service.search("lugar ao sol")
    _wait_until(lambda: len(thumbs) == 2)
    assert got == [(request, results)]
    assert [t[1] for t in thumbs] == ["a", "b"] and thumbs[0][2].endswith(b"/a/mqdefault.jpg")


def test_service_reports_errors_without_prefix(qapp):
    def boom(query):
        raise RuntimeError("ERROR: sem conexão")

    service = YouTubeSearchService(search=boom)
    failed = _collect(service.failed)
    request = service.search("x")
    _wait_until(lambda: failed)
    assert failed == [(request, "sem conexão")]


# ------------------------------------------------------------- integração
class FakeSearch(QObject):
    finished = Signal(int, list)
    failed = Signal(int, str)
    thumbnail_ready = Signal(int, str, bytes)

    def __init__(self):
        super().__init__()
        self.latest = 0
        self.queries = []

    def search(self, query):
        self.latest += 1
        self.queries.append(query)
        return self.latest


def png(color="#ff0000", w=320, h=180) -> bytes:
    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


RESULTS = [VideoResult(f"id{i}", f"Lugar Ao Sol {i}", "Charlie Brown Jr.", 200 + i) for i in range(10)]


@pytest.fixture
def app(qapp, dirs):
    from test_controller import FakeDownloader, FakeSeparator

    from karaoke.controllers import AppController
    from karaoke.models import MusicLibraryModel
    from karaoke.views import MainWindow

    music, separated = dirs
    view = MainWindow()
    ctrl = AppController(view, model=MusicLibraryModel(music, separated), downloader=FakeDownloader(),
                         separator=FakeSeparator(), youtube_search=FakeSearch(),
                         cloud_separator=FakeSeparator())
    ctrl.choose_method = lambda parent, default: default  # sem diálogo nos testes
    ctrl.refresh_library()
    view.show()
    view.activateWindow()
    assert QTest.qWaitForWindowActive(view)
    yield view, ctrl, music
    ctrl.close_youtube_results()
    view.close()
    QTest.qWait(10)


def _search(view, ctrl, text="lugar ao sol"):
    view.url_bar.setText(text)
    QTest.keyClick(view.url_bar, Qt.Key.Key_Return)
    return ctrl.results_page


def test_text_opens_results_page_and_link_still_downloads(app):
    view, ctrl, _ = app
    view.url_bar.setText("youtu.be/abc")
    view.url_button.click()  # o botão faz o mesmo que o Enter
    assert ctrl.downloader.urls == ["https://youtu.be/abc"]
    assert ctrl.results_page is None and not view.showing_page

    page = _search(view, ctrl, "  lugar ao sol ")
    assert ctrl.youtube_search.queries == ["lugar ao sol"]
    assert view.showing_page and view.stack.currentWidget() is page
    assert page.query == "lugar ao sol" and "Pesquisando" in page.status_label.text()
    assert view.url_bar.text() == ""  # o texto foi para o campo da página


def test_results_are_listed_with_thumbnails(app):
    view, ctrl, _ = app
    page = _search(view, ctrl)
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest, RESULTS)
    assert page.list.count() == 10 and page.list.currentRow() == 0
    row = page.row(0)
    assert row.title_label.text() == "Lugar Ao Sol 0"
    assert row.details_label.text() == "Charlie Brown Jr. · 3:20"
    assert "10 resultado(s)" in page.status_label.text()
    assert page.list.hasFocus()  # ↑ ↓ e Enter já funcionam

    ctrl.youtube_search.thumbnail_ready.emit(ctrl.youtube_search.latest, "id0", png())
    ctrl.youtube_search.thumbnail_ready.emit(ctrl.youtube_search.latest, "id1", b"lixo")  # imagem inválida: ignora
    pixmap = row.thumbnail.pixmap()
    assert not pixmap.isNull() and pixmap.size() == row.thumbnail.size()
    assert page.row(1).thumbnail.pixmap().isNull()


def test_stale_results_are_ignored(app):
    view, ctrl, _ = app
    page = _search(view, ctrl, "primeira")
    page.query_edit.setText("segunda")
    QTest.keyClick(page.query_edit, Qt.Key.Key_Return)  # nova pesquisa na própria página
    assert ctrl.youtube_search.queries == ["primeira", "segunda"]
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest - 1, RESULTS[:3])  # resposta da primeira, atrasada
    assert page.list.count() == 0
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest, RESULTS[:2])
    assert page.list.count() == 2


def test_enter_on_result_downloads_and_returns_to_lists(app):
    view, ctrl, _ = app
    page = _search(view, ctrl)
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest, RESULTS)
    QTest.keyClick(page.list, Qt.Key.Key_Down)
    QTest.keyClick(page.list, Qt.Key.Key_Return)
    QApplication.processEvents()
    assert ctrl.downloader.urls == ["https://www.youtube.com/watch?v=id1"]
    assert ctrl.results_page is None and not view.showing_page and view.stack.count() == 1
    assert view.url_bar.hasFocus()
    # respostas que ainda chegarem da pesquisa são ignoradas
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest, RESULTS)


def test_add_button_and_download_queue(app):
    view, ctrl, music = app
    page = _search(view, ctrl)
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest, RESULTS)
    page.row(2).add_button.click()
    assert ctrl.downloader.urls == ["https://www.youtube.com/watch?v=id2"]

    # Outra pesquisa enquanto baixa: vai para a fila
    page = _search(view, ctrl, "outra")
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest, RESULTS)
    page.row(5).add_button.click()
    assert ctrl.downloader.urls == ["https://www.youtube.com/watch?v=id2"]
    assert "Na fila de downloads" in view.statusBar().currentMessage()

    song = add_song(music, "Lugar Ao Sol 2 [id2].webm")
    ctrl.downloader.finished.emit(str(song))  # terminou: começa o próximo
    assert ctrl.downloader.urls[-1] == "https://www.youtube.com/watch?v=id5"
    ctrl.downloader.failed.emit("erro")  # falhou: segue a fila (vazia)
    assert len(ctrl.downloader.urls) == 2 and not ctrl._downloading


@pytest.mark.parametrize("how", ["button", "esc", "ctrl_w"])
def test_closing_results_page(app, how):
    view, ctrl, _ = app
    page = _search(view, ctrl)
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest, RESULTS)
    if how == "button":
        page.close_button.click()
    elif how == "esc":
        QTest.keyClick(page.list, Qt.Key.Key_Escape)
    else:
        QTest.keyClick(page.query_edit, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert ctrl.results_page is None and not view.showing_page
    assert ctrl.downloader.urls == [] and view.url_bar.hasFocus()


def test_link_pasted_on_results_page_downloads(app):
    view, ctrl, _ = app
    page = _search(view, ctrl)
    page.query_edit.setText("https://www.youtube.com/watch?v=zzz")
    page.search_button.click()
    assert ctrl.downloader.urls == ["https://www.youtube.com/watch?v=zzz"]
    assert ctrl.results_page is None and not view.showing_page


def test_open_button_opens_browser(app, monkeypatch):
    import karaoke.controllers.app_controller as app_module

    opened = []
    monkeypatch.setattr(app_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    view, ctrl, _ = app
    page = _search(view, ctrl)
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest, RESULTS)
    page.row(3).open_button.click()
    assert opened == ["https://www.youtube.com/watch?v=id3"]
    assert ctrl.results_page is page  # continua na página


def test_no_results_and_error_messages(app):
    view, ctrl, _ = app
    page = _search(view, ctrl)
    ctrl.youtube_search.finished.emit(ctrl.youtube_search.latest, [])
    assert "Nenhum resultado" in page.status_label.text()
    ctrl.youtube_search.failed.emit(ctrl.youtube_search.latest, "sem conexão")
    assert page.status_label.text() == "Erro na pesquisa: sem conexão"
