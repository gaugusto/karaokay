"""Janela de busca manual de letra no LRCLIB."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from karaoke.models import LyricsState

KIND_LABELS = {
    LyricsState.SYNCED: "Sincronizada",
    LyricsState.PLAIN: "Sem sincronia",
    LyricsState.INSTRUMENTAL: "Instrumental",
    LyricsState.NOT_FOUND: "Sem letra",
}

COLUMNS = ["Música", "Artista", "Álbum", "Duração", "Letra"]


def _format_duration(seconds: float | None, reference: float | None) -> str:
    if not seconds:
        return "—"
    text = f"{int(seconds) // 60}:{int(seconds) % 60:02d}"
    if reference:
        diff = round(seconds - reference)
        text += "  (igual)" if diff == 0 else f"  ({diff:+d} s)"
    return text


class LyricsSearchDialog(QDialog):
    """Campos de artista e música, tabela de resultados e prévia da letra.

    Só exibe e emite sinais; a busca e a gravação ficam no controlador.
    """

    search_requested = Signal(str, str)  # artista, música

    _last_size: QSize | None = None  # tamanho usado da última vez (na sessão)

    def __init__(self, song_title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Buscar letra — {song_title}")
        # Janela comum (não "diálogo preso"): o gerenciador de janelas deixa
        # redimensionar e maximizar; a alça no canto também redimensiona.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setMinimumSize(560, 420)
        self.resize(LyricsSearchDialog._last_size or QSize(860, 640))
        self._records: list[dict] = []
        self._kinds: list[LyricsState] = []
        self._duration: float | None = None

        self.context_note = QLabel()
        self.context_note.setObjectName("hint")
        self.context_note.setWordWrap(True)
        self.context_note.hide()

        intro = QLabel(
            f"Digite o artista e o nome da música para procurar a letra de <b>{song_title}</b> no LRCLIB."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)

        self.artist_edit = QLineEdit()
        self.track_edit = QLineEdit()
        for edit in (self.artist_edit, self.track_edit):
            edit.returnPressed.connect(self._request_search)
        self.search_button = QPushButton("Buscar")
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self._request_search)

        form = QFormLayout()
        form.addRow("Artista:", self.artist_edit)
        track_row = QHBoxLayout()
        track_row.addWidget(self.track_edit, 1)
        track_row.addWidget(self.search_button)
        form.addRow("Música:", track_row)

        self.status_label = QLabel()

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.cellDoubleClicked.connect(lambda *_: self._accept_if_usable())

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Selecione um resultado para ver a letra")

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.preview)
        splitter.setSizes([260, 200])

        self.buttons = QDialogButtonBox()
        self.use_button = self.buttons.addButton("Usar esta letra", QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.use_button.setObjectName("primary")
        self.use_button.setEnabled(False)
        self.buttons.accepted.connect(self._accept_if_usable)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(self.context_note)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.buttons)

    # ------------------------------------------------------------ conteúdo
    def set_opening_player(self, opening: bool) -> None:
        """Aberta ao tentar tocar uma música sem letra: explica e muda o botão."""
        self.context_note.setVisible(opening)
        self.context_note.setText(
            "Esta música ainda não tem letra. Escolha uma para abrir o player." if opening else ""
        )
        self.use_button.setText("Usar e abrir o player" if opening else "Usar esta letra")

    def set_query(self, artist: str, track: str) -> None:
        self.artist_edit.setText(artist)
        self.track_edit.setText(track)

    def set_reference_duration(self, seconds: float | None) -> None:
        self._duration = seconds

    def set_searching(self, searching: bool) -> None:
        self.search_button.setEnabled(not searching)
        if searching:
            self.status_label.setText("Buscando no LRCLIB…")

    def show_error(self, message: str) -> None:
        self.set_searching(False)
        self.status_label.setText(f"Erro na busca: {message}")

    def set_results(self, records: list[dict], kinds: list[LyricsState]) -> None:
        self.set_searching(False)
        self._records, self._kinds = records, kinds
        self.table.setRowCount(0)
        self.preview.clear()
        self.use_button.setObjectName("primary")
        self.use_button.setEnabled(False)
        for row, (record, kind) in enumerate(zip(records, kinds)):
            self.table.insertRow(row)
            values = [
                record.get("trackName") or "",
                record.get("artistName") or "",
                record.get("albumName") or "",
                _format_duration(record.get("duration"), self._duration),
                KIND_LABELS[kind],
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if kind not in (LyricsState.SYNCED, LyricsState.PLAIN):
                    item.setForeground(self.palette().placeholderText())
                self.table.setItem(row, col, item)
        if records:
            synced = sum(k is LyricsState.SYNCED for k in kinds)
            self.status_label.setText(
                f"{len(records)} resultado(s), {synced} com letra sincronizada. "
                "Prefira duração parecida com a do áudio."
            )
            self.table.selectRow(0)
        else:
            self.status_label.setText("Nenhum resultado. Tente outra grafia ou só o nome da música.")

    # ---------------------------------------------------------- consulta
    def selected_record(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        return self._records[rows[0].row()] if rows else None

    def _selected_kind(self) -> LyricsState | None:
        rows = self.table.selectionModel().selectedRows()
        return self._kinds[rows[0].row()] if rows else None

    # ------------------------------------------------------------ eventos
    def _request_search(self) -> None:
        artist, track = self.artist_edit.text().strip(), self.track_edit.text().strip()
        if not (artist or track):
            self.status_label.setText("Digite pelo menos o nome da música.")
            return
        self.set_searching(True)
        self.search_requested.emit(artist, track)

    def _on_selection(self) -> None:
        record, kind = self.selected_record(), self._selected_kind()
        usable = kind in (LyricsState.SYNCED, LyricsState.PLAIN)
        self.use_button.setEnabled(usable)
        if record is None:
            self.preview.clear()
        elif kind is LyricsState.SYNCED:
            self.preview.setPlainText(record.get("syncedLyrics") or "")
        elif usable:
            self.preview.setPlainText(record.get("plainLyrics") or record.get("syncedLyrics") or "")
        else:
            self.preview.setPlainText("(este resultado não tem letra)")

    def _accept_if_usable(self) -> None:
        if self.use_button.isEnabled():
            self.accept()

    def done(self, result: int) -> None:
        LyricsSearchDialog._last_size = self.size()  # próxima janela abre do mesmo tamanho
        super().done(result)
