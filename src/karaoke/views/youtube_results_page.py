"""Página com os resultados da pesquisa no YouTube (ocupa a janela principal)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QPainter, QPainterPath, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from karaoke.services.youtube_search import VideoResult

THUMB_SIZE = QSize(128, 72)
ROW_HEIGHT = 96


def rounded_thumbnail(data: bytes, size: QSize = THUMB_SIZE, radius: float = 8) -> QPixmap | None:
    """Miniatura cortada para 16:9 com cantos arredondados (None se inválida)."""
    source = QPixmap()
    if not data or not source.loadFromData(data):
        return None
    ratio = source.devicePixelRatio()
    scaled = source.scaled(
        size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
    )
    x, y = (scaled.width() - size.width()) // 2, (scaled.height() - size.height()) // 2
    result = QPixmap(size)
    result.setDevicePixelRatio(ratio)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled, x, y, size.width(), size.height())
    painter.end()
    return result


class ResultRow(QWidget):
    """Um resultado: miniatura, título, canal · duração, ▶ e "Adicionar"."""

    add_clicked = Signal(object)   # VideoResult
    open_clicked = Signal(object)  # VideoResult

    def __init__(self, result: VideoResult, parent=None) -> None:
        super().__init__(parent)
        self.result = result
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.thumbnail = QLabel()
        self.thumbnail.setObjectName("thumbnail")
        self.thumbnail.setFixedSize(THUMB_SIZE)

        self.title_label = QLabel(result.title)
        self.title_label.setObjectName("resultTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(46)  # até duas linhas
        details = " · ".join(part for part in (result.channel, result.duration_text) if part)
        self.details_label = QLabel(details)
        self.details_label.setObjectName("hint")
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addStretch(1)
        text.addWidget(self.title_label)
        text.addWidget(self.details_label)
        text.addStretch(1)

        self.open_button = QPushButton("▶")
        self.open_button.setObjectName("fontButton")
        self.open_button.setFixedSize(46, 40)
        self.open_button.setToolTip("Ver no YouTube (abre o navegador)")
        self.open_button.setAccessibleName("Ver no YouTube")
        self.open_button.clicked.connect(lambda: self.open_clicked.emit(self.result))
        self.add_button = QPushButton("Adicionar")
        self.add_button.setObjectName("primary")
        self.add_button.setToolTip("Baixar esta música e mandar para o processamento (Enter)")
        self.add_button.clicked.connect(lambda: self.add_clicked.emit(self.result))
        for button in (self.open_button, self.add_button):
            button.setAutoDefault(True)  # Enter aciona o botão com foco
            button.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # teclado: ↑ ↓ e Enter na lista

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)
        layout.addWidget(self.thumbnail)
        layout.addLayout(text, 1)
        layout.addWidget(self.open_button)
        layout.addWidget(self.add_button)

    def set_thumbnail(self, data: bytes) -> bool:
        pixmap = rounded_thumbnail(data)
        if pixmap is None:
            return False
        self.thumbnail.setPixmap(pixmap)
        return True


class YouTubeResultsPage(QWidget):
    """Campo de pesquisa e os primeiros resultados do YouTube.

    Só exibe e emite sinais; a pesquisa e o download ficam no controlador.
    """

    submitted = Signal(str)       # texto do campo (nova pesquisa ou link)
    add_requested = Signal(object)   # VideoResult
    open_requested = Signal(object)  # VideoResult
    rejected = Signal()           # ✕ / Esc / Ctrl+W

    def __init__(self, query: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("youtubeResultsPage")
        self._rows: dict[str, ResultRow] = {}
        self._shown_once = False

        # Cabeçalho: ✕ à esquerda e título centralizado (como no player)
        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("fontButton")
        self.close_button.setFixedSize(46, 40)
        self.close_button.setToolTip("Voltar às listas (Esc)")
        self.close_button.setAccessibleName("Fechar a pesquisa")
        self.close_button.clicked.connect(self.reject)
        title = QLabel("Pesquisar no YouTube")
        title.setObjectName("songTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_bar = QHBoxLayout()
        top_bar.addWidget(self.close_button)
        top_bar.addWidget(title, 1)
        top_bar.addSpacing(46)  # equilibra o ✕

        # Campo de pesquisa (aceita também um link)
        self.query_edit = QLineEdit(query)
        self.query_edit.setObjectName("urlBar")
        self.query_edit.setPlaceholderText("Nome da música ou link do YouTube")
        self.query_edit.setClearButtonEnabled(True)
        self.query_edit.setAccessibleName("Pesquisa")
        self.query_edit.returnPressed.connect(self._submit)
        self.search_button = QPushButton("Buscar")
        self.search_button.setObjectName("primary")
        self.search_button.setAutoDefault(True)
        self.search_button.clicked.connect(self._submit)
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        search_row.addWidget(self.query_edit, 1)
        search_row.addWidget(self.search_button)

        self.status_label = QLabel()
        self.status_label.setObjectName("hint")

        self.list = QListWidget()
        self.list.setObjectName("results")
        self.list.setAccessibleName("Resultados do YouTube")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setSpacing(3)
        self.list.setFrameShape(QListWidget.Shape.NoFrame)  # o foco aparece no cartão selecionado
        self.list.itemActivated.connect(self._on_activated)  # Enter / dois cliques

        self.close_button.setAutoDefault(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 16)
        layout.setSpacing(12)
        layout.addLayout(top_bar)
        layout.addLayout(search_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.list, 1)

        for keys in (QKeySequence(Qt.Key.Key_Escape), QKeySequence.StandardKey.Close):  # Close: Ctrl+W e Ctrl+F4
            shortcut = QShortcut(keys, self, self.reject)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

        for first, second in zip(
            [self.query_edit, self.search_button, self.list], [self.search_button, self.list, self.close_button]
        ):
            QWidget.setTabOrder(first, second)

    # ------------------------------------------------------------ conteúdo
    @property
    def query(self) -> str:
        return self.query_edit.text().strip()

    def set_query(self, text: str) -> None:
        self.query_edit.setText(text)

    def set_searching(self, query: str) -> None:
        self.query_edit.setText(query)
        self.list.clear()
        self._rows.clear()
        self.status_label.setText(f"Pesquisando “{query}” no YouTube…")

    def show_error(self, message: str) -> None:
        self.status_label.setText(f"Erro na pesquisa: {message}")

    def set_results(self, results: list[VideoResult]) -> None:
        self.list.clear()
        self._rows.clear()
        for result in results:
            row = ResultRow(result)
            row.add_clicked.connect(self.add_requested)
            row.open_clicked.connect(self.open_requested)
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            item.setData(Qt.ItemDataRole.UserRole, result.id)
            item.setToolTip(result.title)
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            self._rows[result.id] = row
        if results:
            self.status_label.setText(
                f"{len(results)} resultado(s). ↑ ↓ escolhe, Enter adiciona; ▶ abre no navegador."
            )
            self.list.setCurrentRow(0)
            if self.query_edit.hasFocus() or self.search_button.hasFocus() or not self.isVisible():
                self.list.setFocus()
        else:
            self.status_label.setText("Nenhum resultado. Tente outras palavras.")

    def set_thumbnail(self, video_id: str, data: bytes) -> None:
        row = self._rows.get(video_id)
        if row is not None:
            row.set_thumbnail(data)

    def row(self, index: int) -> ResultRow:
        return self.list.itemWidget(self.list.item(index))

    # ------------------------------------------------------------ eventos
    def _submit(self) -> None:
        if self.query:
            self.submitted.emit(self.query)

    def _on_activated(self, item: QListWidgetItem) -> None:
        row = self.list.itemWidget(item)
        if row is not None and row.add_button.isEnabled():
            row.add_button.click()

    def keyPressEvent(self, event) -> None:
        """↓ no campo de pesquisa vai para os resultados."""
        if self.query_edit.hasFocus() and event.key() == Qt.Key.Key_Down and self.list.count():
            self.list.setFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shown_once:
            self._shown_once = True
            self.query_edit.setFocus()

    def reject(self) -> None:
        self.rejected.emit()

