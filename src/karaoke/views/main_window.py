"""Janela principal: só layout, exibição e sinais."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QKeySequence, QShortcut
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

from karaoke.models import LyricsState, MusicLibraryModel
from karaoke.views.song_delegate import PendingSongDelegate, ProcessedSongDelegate, song_tooltip


class _SongListView(QListView):
    delete_pressed = Signal(list)  # caminhos das músicas selecionadas

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.setMouseTracking(True)  # destaque do cartão sob o mouse
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        # Ctrl/Shift + clique selecionam várias músicas para excluir de uma vez
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)

    def selected_paths(self) -> list[str]:
        rows = sorted(self.selectionModel().selectedRows(), key=lambda i: i.row())
        if not rows and self.currentIndex().isValid():
            rows = [self.currentIndex()]
        paths = [index.data(MusicLibraryModel.PathRole) for index in rows]
        return [p for p in paths if p]

    def focusInEvent(self, event) -> None:
        """Ao chegar pelo Tab, já marca a primeira música (se nenhuma estiver)."""
        super().focusInEvent(event)
        model = self.model()
        if model is not None and not self.currentIndex().isValid() and model.rowCount():
            self.setCurrentIndex(model.index(0, 0))

    def event(self, event) -> bool:
        """Tecla de menu / Shift+F10: abre o menu da música atual (e não a do
        ponto central da lista, que é o que o Qt usaria)."""
        if (
            event.type() == QEvent.Type.ContextMenu
            and event.reason() == QContextMenuEvent.Reason.Keyboard
            and self.currentIndex().isValid()
        ):
            self.customContextMenuRequested.emit(self.visualRect(self.currentIndex()).center())
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        menu_key = event.key() == Qt.Key.Key_Menu or (
            event.key() == Qt.Key.Key_F10 and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
        )
        if (
            menu_key
            and self.currentIndex().isValid()
            and self.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
        ):  # tecla de menu ou Shift+F10 (para teclados sem ela)
            self.customContextMenuRequested.emit(self.visualRect(self.currentIndex()).center())
            event.accept()
            return
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
        self.header.setObjectName("sectionHeader")
        self.view = _SongListView()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
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
    manual_lyrics_requested = Signal(str)  # botão direito > Letra > Buscar letra manualmente…
    auto_sync_requested = Signal(str)      # botão direito > Letra > Sincronizar automaticamente
    restore_lyrics_requested = Signal(str)  # botão direito > Letra > Restaurar letra original

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Karaokê")
        self.resize(1100, 760)

        # Cabeçalho
        title = QLabel("Karaokê")
        title.setObjectName("appTitle")
        subtitle = QLabel("Cole um link do YouTube")
        subtitle.setObjectName("appSubtitle")

        # Barra de links no topo
        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("urlBar")
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
        splitter.setSizes([320, 380])

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 22, 28, 16)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(4)
        layout.addWidget(self.url_bar)
        layout.addSpacing(6)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        # Barra de status: progresso do download
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        self.statusBar().addPermanentWidget(self.progress_bar)

        # Teclado: Tab alterna barra de link → "A processar" → "Processadas";
        # Ctrl+L volta para a barra de link
        QWidget.setTabOrder(self.url_bar, self.pending_panel.view)
        QWidget.setTabOrder(self.pending_panel.view, self.processed_panel.view)
        QShortcut(QKeySequence("Ctrl+L"), self, self.focus_url_bar)
        self.url_bar.setToolTip("Cole um link do YouTube e pressione Enter (Ctrl+L)")
        self.pending_panel.view.setAccessibleName("Músicas a processar")
        self.processed_panel.view.setAccessibleName("Músicas processadas")

        # Definido pelo controlador: decide se a janela pode fechar
        self.close_guard: Callable[[], bool] | None = None

    def focus_url_bar(self) -> None:
        self.url_bar.setFocus()
        self.url_bar.selectAll()

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
        menu = self.build_processed_menu(index)
        menu.exec(view.viewport().mapToGlobal(pos))

    def build_processed_menu(self, index: QModelIndex) -> QMenu:
        """Menu do botão direito de uma música processada (com o submenu Letra)."""
        path = index.data(MusicLibraryModel.PathRole)
        song = index.data(MusicLibraryModel.SongRole)
        menu = QMenu(self.processed_panel.view)
        menu.addAction("Abrir no player", lambda: self.play_requested.emit(path))

        lyrics = menu.addMenu("Letra")
        auto = lyrics.addAction(
            "Sincronizar automaticamente com os vocais", lambda: self.auto_sync_requested.emit(path)
        )
        synced = song is not None and song.lyrics_state is LyricsState.SYNCED
        auto.setEnabled(synced)
        if not synced:
            auto.setText("Sincronizar automaticamente (precisa de letra sincronizada)")
        restore = lyrics.addAction(
            "Restaurar letra original", lambda: self.restore_lyrics_requested.emit(path)
        )
        backup = song.lyrics_backup_path if song is not None else None
        restore.setEnabled(bool(backup and backup.is_file()))
        lyrics.addSeparator()
        lyrics.addAction("Buscar letra manualmente…", lambda: self.manual_lyrics_requested.emit(path))

        menu.addSeparator()
        menu.addAction("Excluir…", lambda: self.delete_requested.emit([path]))
        return menu

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
