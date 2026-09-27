"""Janela principal: só layout, exibição e sinais."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QProgressBar,
    QSplitter,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from karaoke.models import MusicLibraryModel
from karaoke.views.song_delegate import PendingSongDelegate, ProcessedSongDelegate, song_tooltip


class _SongListView(QListView):
    delete_pressed = Signal(list)  # caminhos das músicas selecionadas

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        # Ctrl/Shift + clique selecionam várias músicas para excluir de uma vez
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)

    def selected_paths(self) -> list[str]:
        rows = sorted(self.selectionModel().selectedRows(), key=lambda i: i.row())
        if not rows and self.currentIndex().isValid():
            rows = [self.currentIndex()]
        paths = [index.data(MusicLibraryModel.PathRole) for index in rows]
        return [p for p in paths if p]

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete and self.model() is not None:
            paths = self.selected_paths()
            if paths:
                self.delete_pressed.emit(paths)
            event.accept()
            return
        super().keyPressEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            index = self.indexAt(event.pos())
            if index.isValid():
                QToolTip.showText(event.globalPos(), song_tooltip(index), self)
                return True
        return super().viewportEvent(event)


class _SongPanel(QWidget):
    """Título com contagem + lista de músicas."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self.header = QLabel()
        font = self.header.font()
        font.setBold(True)
        self.header.setFont(font)
        self.view = _SongListView()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.header)
        layout.addWidget(self.view, 1)

    def set_model(self, model: QAbstractItemModel) -> None:
        self.view.setModel(model)
        for sig in (model.rowsInserted, model.rowsRemoved, model.modelReset, model.layoutChanged):
            sig.connect(self._update_header)
        self._update_header()

    def _update_header(self, *_args) -> None:
        model = self.view.model()
        n = model.rowCount() if model else 0
        self.header.setText(f"{self._title} ({n})")
        self.view.viewport().update()  # renumera a posição na fila

    def select(self, index: QModelIndex) -> None:
        if index.isValid():
            self.view.setCurrentIndex(index)
            self.view.scrollTo(index)


class MainWindow(QMainWindow):
    url_submitted = Signal(str)
    play_requested = Signal(str)  # caminho da música processada (dois cliques)
    delete_requested = Signal(list)  # caminhos das músicas selecionadas (tecla Delete)
    manual_lyrics_requested = Signal(str)  # botão direito > Buscar letra manualmente…

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Karaokê")
        self.resize(1024, 640)

        # Barra de links no topo
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Cole um link do YouTube e pressione Enter")
        self.url_bar.setClearButtonEnabled(True)
        self.url_bar.returnPressed.connect(self._on_return_pressed)

        # Duas listas: a processar (fila) e processadas
        self.pending_panel = _SongPanel("A processar")
        self.pending_panel.view.setItemDelegate(PendingSongDelegate(self.pending_panel.view))
        self.processed_panel = _SongPanel("Processadas")
        self.processed_panel.view.setItemDelegate(ProcessedSongDelegate(self.processed_panel.view))
        self.processed_panel.view.doubleClicked.connect(self._on_processed_activated)
        self.processed_panel.view.activated.connect(self._on_processed_activated)  # Enter
        self.processed_panel.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.processed_panel.view.customContextMenuRequested.connect(self._show_processed_menu)
        self.pending_panel.view.delete_pressed.connect(self.delete_requested)
        self.processed_panel.view.delete_pressed.connect(self.delete_requested)

        splitter = QSplitter(Qt.Orientation.Vertical)  # a processar em cima, processadas embaixo
        splitter.addWidget(self.pending_panel)
        splitter.addWidget(self.processed_panel)
        splitter.setChildrenCollapsible(False)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.url_bar)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        # Barra de status: progresso do download
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.hide()
        self.statusBar().addPermanentWidget(self.progress_bar)

        # Definido pelo controlador: decide se a janela pode fechar
        self.close_guard: Callable[[], bool] | None = None

    # ------------------------------------------------------------- modelos
    def set_models(self, pending: QAbstractItemModel, processed: QAbstractItemModel) -> None:
        self.pending_panel.set_model(pending)
        self.processed_panel.set_model(processed)

    def select_pending(self, index: QModelIndex) -> None:
        self.pending_panel.select(index)

    def _show_processed_menu(self, pos) -> None:
        view = self.processed_panel.view
        index = view.indexAt(pos)
        if not index.isValid():
            return
        path = index.data(MusicLibraryModel.PathRole)
        menu = QMenu(view)
        menu.addAction("Abrir no player", lambda: self.play_requested.emit(path))
        menu.addAction("Buscar letra manualmente…", lambda: self.manual_lyrics_requested.emit(path))
        menu.addSeparator()
        menu.addAction("Excluir…", lambda: self.delete_requested.emit([path]))
        menu.exec(view.viewport().mapToGlobal(pos))

    def _on_processed_activated(self, index: QModelIndex) -> None:
        path = index.data(MusicLibraryModel.PathRole)
        if path:
            self.play_requested.emit(path)

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

    # ------------------------------------------------------------ mensagens
    def show_message(self, text: str, timeout_ms: int = 0) -> None:
        self.statusBar().showMessage(text, timeout_ms)

    # --------------------------------------------------------------- fechar
    def closeEvent(self, event) -> None:
        if self.close_guard is not None and not self.close_guard():
            event.ignore()
            return
        super().closeEvent(event)
