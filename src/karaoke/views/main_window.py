"""Janela principal: só layout, exibição e sinais."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QAbstractItemModel, QEvent, QItemSelectionModel, QModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from karaoke.views.splitter import GripSplitter
from karaoke.models import MusicLibraryModel
from karaoke.views.song_delegate import PendingSongDelegate, ProcessedSongDelegate, RowAction, song_tooltip


class _SongListView(QListView):
    delete_pressed = Signal(list)  # caminhos das músicas selecionadas
    action_triggered = Signal(str, str)  # chave do ícone ("play", "search", "delete"), caminho da música

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.setMouseTracking(True)  # destaque do cartão e do ícone sob o mouse
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
            if self.selectionModel().hasSelection():  # não desfaz a seleção feita
                self.selectionModel().setCurrentIndex(
                    model.index(0, 0), QItemSelectionModel.SelectionFlag.NoUpdate
                )
            else:
                self.setCurrentIndex(model.index(0, 0))

    # ------------------------------------------------------ ícones de ação
    def _delegate(self):
        delegate = self.itemDelegate()
        return delegate if hasattr(delegate, "action_at") else None

    def actions_for(self, index: QModelIndex) -> list[RowAction]:
        delegate = self._delegate()
        song = index.data(MusicLibraryModel.SongRole) if index.isValid() else None
        return delegate.actions(song) if delegate is not None and song is not None else []

    def action_rect(self, index: QModelIndex, key: str) -> QRect:
        """Área do ícone ``key`` na linha ``index`` (coordenadas do viewport)."""
        delegate = self._delegate()
        song = index.data(MusicLibraryModel.SongRole)
        for action, box in delegate.action_rects(self.visualRect(index), song):
            if action.key == key:
                return box.toRect()
        return QRect()

    def action_at(self, pos) -> tuple[QModelIndex, RowAction | None]:
        index = self.indexAt(pos)
        delegate = self._delegate()
        if not index.isValid() or delegate is None:
            return index, None
        song = index.data(MusicLibraryModel.SongRole)
        return index, delegate.action_at(self.visualRect(index), song, pos)

    def _set_marker(self, attr: str, value) -> None:
        delegate = self._delegate()
        if delegate is None or getattr(delegate, attr) == value:
            return
        setattr(delegate, attr, value)
        self.viewport().update()

    def _trigger(self, index: QModelIndex, action: RowAction) -> None:
        path = index.data(MusicLibraryModel.PathRole)
        if path and action.enabled:
            self.action_triggered.emit(action.key, path)

    def mouseMoveEvent(self, event) -> None:
        index, action = self.action_at(event.position().toPoint())
        self._set_marker("hovered_action", (index.row(), action.key) if action else None)
        if action is not None and event.buttons() != Qt.MouseButton.NoButton:
            event.accept()  # arrastar a partir de um ícone não seleciona outras músicas
            return
        super().mouseMoveEvent(event)
        if action is not None and action.enabled:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().unsetCursor()

    def leaveEvent(self, event) -> None:
        self._set_marker("hovered_action", None)
        self.viewport().unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        index, action = self.action_at(event.position().toPoint())
        if action is None:
            super().mousePressEvent(event)
            return
        # Clique num ícone: marca a música, mas não mexe na seleção múltipla
        if event.button() == Qt.MouseButton.LeftButton and action.enabled:
            self._set_marker("pressed_action", (index.row(), action.key))
            if self.selectionModel().isSelected(index):
                self.selectionModel().setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
            else:
                self.setCurrentIndex(index)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        delegate = self._delegate()
        pressed = delegate.pressed_action if delegate is not None else None
        if pressed is None:
            super().mouseReleaseEvent(event)
            return
        self._set_marker("pressed_action", None)
        index, action = self.action_at(event.position().toPoint())
        if action is not None and (index.row(), action.key) == pressed:
            self._trigger(index, action)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        _, action = self.action_at(event.position().toPoint())
        if action is not None:
            event.accept()  # dois cliques num ícone não abrem o player
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete and self.model() is not None:
            paths = self.selected_paths()
            if paths:
                self.delete_pressed.emit(paths)
            event.accept()
            return
        # Atalho do ícone da lupa (Ctrl+B) na música atual
        index = self.currentIndex()
        if index.isValid() and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            sequence = QKeySequence(event.keyCombination())
            for action in self.actions_for(index):
                if action.matches(sequence):
                    self._trigger(index, action)
                    event.accept()
                    return
        super().keyPressEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            index, action = self.action_at(event.pos())
            if action is not None:
                QToolTip.showText(event.globalPos(), action.full_tooltip, self, self.action_rect(index, action.key))
                return True
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
    manual_lyrics_requested = Signal(str)  # ícone da lupa (Ctrl+B)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Karaokê")
        self.resize(1100, 760)

        # Cabeçalho
        title = QLabel("Karaokê")
        title.setObjectName("appTitle")
        subtitle = QLabel("Cole um link do YouTube ou pesquise pelo nome da música")
        subtitle.setObjectName("appSubtitle")

        # Barra de links no topo
        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("urlBar")
        self.url_bar.setPlaceholderText("Link do YouTube ou nome da música")
        self.url_bar.setClearButtonEnabled(True)
        self.url_bar.returnPressed.connect(self._on_return_pressed)
        self.url_button = QPushButton("Buscar")
        self.url_button.setObjectName("primary")
        self.url_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # no teclado, Enter na barra faz o mesmo
        self.url_button.setMinimumHeight(46)
        self.url_button.clicked.connect(self._on_return_pressed)
        url_row = QHBoxLayout()
        url_row.setSpacing(10)
        url_row.addWidget(self.url_bar, 1)
        url_row.addWidget(self.url_button)

        # Duas listas: a processar (fila) e processadas
        self.pending_panel = _SongPanel("A processar")
        self.pending_panel.view.setItemDelegate(PendingSongDelegate(self.pending_panel.view))
        self.processed_panel = _SongPanel("Processadas")
        self.processed_panel.view.setItemDelegate(ProcessedSongDelegate(self.processed_panel.view))
        self.processed_panel.view.doubleClicked.connect(self._on_processed_activated)
        self.processed_panel.view.activated.connect(self._on_processed_activated)  # Enter
        self.pending_panel.view.action_triggered.connect(self._on_row_action)
        self.processed_panel.view.action_triggered.connect(self._on_row_action)
        self.pending_panel.view.delete_pressed.connect(self.delete_requested)
        self.processed_panel.view.delete_pressed.connect(self.delete_requested)

        splitter = GripSplitter(Qt.Orientation.Vertical)  # a processar em cima, processadas embaixo
        splitter.addWidget(self.pending_panel)
        splitter.addWidget(self.processed_panel)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([320, 380])

        self.library_page = QWidget()
        layout = QVBoxLayout(self.library_page)
        layout.setContentsMargins(28, 22, 28, 16)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(4)
        layout.addLayout(url_row)
        layout.addSpacing(6)
        layout.addWidget(splitter, 1)

        # Páginas: biblioteca (listas) e, quando aberto, o player
        self.stack = QStackedWidget()
        self.stack.addWidget(self.library_page)
        self.setCentralWidget(self.stack)

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
        self.url_bar.setToolTip(
            "Link do YouTube: baixa a música. Outro texto: pesquisa no YouTube. Enter confirma (Ctrl+L)"
        )
        self.pending_panel.view.setAccessibleName("Músicas a processar")
        self.processed_panel.view.setAccessibleName("Músicas processadas")

        # Definido pelo controlador: decide se a janela pode fechar
        self.close_guard: Callable[[], bool] | None = None

    def focus_url_bar(self) -> None:
        if self.stack.currentWidget() is not self.library_page:
            return  # com o player ou a busca de letra na tela, Ctrl+L não faz nada
        self.url_bar.setFocus()
        self.url_bar.selectAll()

    # --------------------------------------------------------------- páginas
    @property
    def showing_page(self) -> bool:
        return self.stack.currentWidget() is not self.library_page

    def show_page(self, page: QWidget, title: str = "") -> None:
        """Uma página (player, busca de letra) ocupa a janela principal."""
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self.setWindowTitle(f"Karaokê — {title}" if title else "Karaokê")

    def show_library(self, page: QWidget | None = None, select: QModelIndex | None = None) -> None:
        """Tira a página fechada e volta para as listas, com ``select`` selecionada."""
        if page is not None and self.stack.indexOf(page) >= 0:
            was_current = self.stack.currentWidget() is page
            self.stack.removeWidget(page)
            if not was_current:
                return  # outra página continua na tela
        self.stack.setCurrentWidget(self.library_page)
        self.setWindowTitle("Karaokê")
        view = self.processed_panel.view
        if select is not None and select.isValid():
            view.setCurrentIndex(select)
            view.scrollTo(select)
        view.setFocus()

    # ------------------------------------------------------------- modelos
    def set_models(self, pending: QAbstractItemModel, processed: QAbstractItemModel) -> None:
        self.pending_panel.set_model(pending)
        self.processed_panel.set_model(processed)

    def select_pending(self, index: QModelIndex) -> None:
        self.pending_panel.select(index)

    def _on_row_action(self, key: str, path: str) -> None:
        """Ícone clicado (ou atalho) numa música das listas."""
        signals = {
            "play": self.play_requested,
            "search": self.manual_lyrics_requested,
        }
        if key == "delete":
            self.delete_requested.emit([path])
        elif key in signals:
            signals[key].emit(path)

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
        """A barra continua livre: dá para pesquisar e enfileirar outros downloads."""
        self.progress_bar.setVisible(running)
        if running:
            self.progress_bar.setValue(0)

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
