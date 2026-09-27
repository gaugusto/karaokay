"""Janela principal: só layout, exibição e sinais."""

from __future__ import annotations

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QProgressBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from karaoke.views.song_delegate import SongDelegate, song_tooltip


class _SongListView(QListView):
    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            index = self.indexAt(event.pos())
            if index.isValid():
                QToolTip.showText(event.globalPos(), song_tooltip(index), self)
                return True
        return super().viewportEvent(event)


class MainWindow(QMainWindow):
    url_submitted = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Karaokê")
        self.resize(1024, 640)

        # Barra de links no topo
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Cole um link do YouTube e pressione Enter")
        self.url_bar.setClearButtonEnabled(True)
        self.url_bar.returnPressed.connect(self._on_return_pressed)

        # Lista de músicas
        self.count_label = QLabel()
        self.song_list = _SongListView()
        self.song_list.setAlternatingRowColors(True)
        self.song_list.setItemDelegate(SongDelegate(self.song_list))

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.url_bar)
        layout.addWidget(self.count_label)
        layout.addWidget(self.song_list, 1)
        self.setCentralWidget(central)

        # Barra de status: progresso do download e indicador da separação
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.hide()
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.separation_label = QLabel()
        self.separation_label.hide()
        self.statusBar().addPermanentWidget(self.separation_label)

    # ------------------------------------------------------------- modelo
    def set_model(self, model: QAbstractItemModel) -> None:
        self.song_list.setModel(model)
        model.rowsInserted.connect(self._update_count)
        model.rowsRemoved.connect(self._update_count)
        model.modelReset.connect(self._update_count)
        self._update_count()

    def _update_count(self, *_args) -> None:
        model = self.song_list.model()
        n = model.rowCount() if model else 0
        self.count_label.setText("1 música" if n == 1 else f"{n} músicas")

    def select(self, index: QModelIndex) -> None:
        if index.isValid():
            self.song_list.setCurrentIndex(index)
            self.song_list.scrollTo(index)

    # ------------------------------------------------------------ download
    def _on_return_pressed(self) -> None:
        text = self.url_bar.text().strip()
        if text:
            self.url_submitted.emit(text)

    def set_download_running(self, running: bool) -> None:
        self.url_bar.setEnabled(not running)
        self.progress_bar.setVisible(running)
        if running:
            self.progress_bar.setValue(0)
        else:
            self.url_bar.setFocus()

    def set_download_progress(self, percent: float) -> None:
        self.progress_bar.setValue(int(percent))

    def clear_url(self) -> None:
        self.url_bar.clear()

    # ----------------------------------------------------------- separação
    def set_separation_count(self, n: int) -> None:
        self.separation_label.setVisible(n > 0)
        self.separation_label.setText("Separando 1 música" if n == 1 else f"Separando {n} músicas")

    # ------------------------------------------------------------ mensagens
    def show_message(self, text: str, timeout_ms: int = 0) -> None:
        self.statusBar().showMessage(text, timeout_ms)
