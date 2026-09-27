"""Janela principal do aplicativo."""

from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from karaoke.downloader import AudioDownloader, is_youtube_url
from karaoke.library import MusicLibrary
from karaoke.paths import MUSIC_DIR


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Karaokê")
        self.resize(1024, 640)

        self._thread: QThread | None = None
        self._worker: AudioDownloader | None = None

        # Barra de links no topo
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Cole um link do YouTube e pressione Enter")
        self.url_bar.setClearButtonEnabled(True)
        self.url_bar.returnPressed.connect(self._start_download)

        # Lista de músicas
        self.library = MusicLibrary(MUSIC_DIR)
        self.count_label = QLabel()
        self.library.model().rowsInserted.connect(self._update_count)
        self.library.model().rowsRemoved.connect(self._update_count)
        self.library.model().modelReset.connect(self._update_count)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.url_bar)
        layout.addWidget(self.count_label)
        layout.addWidget(self.library, 1)
        self.setCentralWidget(central)

        # Progresso do download na barra de status
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.hide()
        self.statusBar().addPermanentWidget(self.progress_bar)

        self._update_count()

    # ---------------------------------------------------------------- lista
    def _update_count(self, *_args) -> None:
        n = self.library.count()
        self.count_label.setText("1 música" if n == 1 else f"{n} músicas")

    # ------------------------------------------------------------- download
    def _start_download(self) -> None:
        url = self.url_bar.text().strip()
        if not url:
            return
        if not is_youtube_url(url):
            self.statusBar().showMessage("Isso não parece um link do YouTube.", 5000)
            return
        if self._thread is not None:
            self.statusBar().showMessage("Aguarde o download atual terminar.", 5000)
            return

        self.url_bar.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self._thread = QThread(self)
        self._worker = AudioDownloader(url, MUSIC_DIR)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_download_progress)
        self._worker.status.connect(self.statusBar().showMessage)
        self._worker.finished.connect(self._on_download_finished)
        self._worker.failed.connect(self._on_download_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_download)

        self._thread.start()

    def _on_download_progress(self, percent: float) -> None:
        self.progress_bar.setValue(int(percent))

    def _on_download_finished(self, path: str) -> None:
        self.url_bar.clear()
        self.library.refresh()
        self.library.select_path(path)
        self.statusBar().showMessage("Download concluído.", 5000)

    def _on_download_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"Falha no download: {message}", 10000)

    def _cleanup_download(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self.progress_bar.hide()
        self.url_bar.setEnabled(True)
        self.url_bar.setFocus()

    def closeEvent(self, event) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)
