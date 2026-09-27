"""Janela do player: letra sincronizada, play/pause e volumes."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from karaoke.models.lrc import Lyrics


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class _VolumeSlider(QWidget):
    changed = Signal(float)  # 0.0 – 1.0

    def __init__(self, label: str, value: int = 100, parent=None) -> None:
        super().__init__(parent)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(value)
        self.slider.setMinimumWidth(120)
        self.value_label = QLabel(f"{value}%")
        self.value_label.setMinimumWidth(40)
        self.slider.valueChanged.connect(self._on_changed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value_label)

    def _on_changed(self, value: int) -> None:
        self.value_label.setText(f"{value}%")
        self.changed.emit(value / 100)


class PlayerWindow(QWidget):
    toggle_requested = Signal()
    seek_requested = Signal(float)           # segundos
    seek_relative_requested = Signal(float)  # segundos (+/-)
    vocal_volume_changed = Signal(float)
    instrumental_volume_changed = Signal(float)
    closed = Signal()

    LINE_FONT_SIZE = 18

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Karaokê — Player")
        self.resize(760, 620)
        self._lyrics = Lyrics()
        self._current_line = -1
        self._duration = 0.0
        self._slider_held = False

        self.title_label = QLabel()
        title_font = self.title_label.font()
        title_font.setPointSize(title_font.pointSize() + 4)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)

        self.lyrics_note = QLabel()
        self.lyrics_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lyrics_note.setEnabled(False)  # cinza

        # Letra: um verso por linha, centralizada
        self.lyrics_view = QListWidget()
        self.lyrics_view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.lyrics_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lyrics_view.setWordWrap(True)
        self.lyrics_view.setSpacing(4)
        self.lyrics_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.lyrics_view.itemClicked.connect(self._on_line_clicked)

        # Controles
        self.play_button = QPushButton()
        self.play_button.setFixedWidth(48)
        self.play_button.clicked.connect(self.toggle_requested)
        self.set_playing(False)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.time_label = QLabel("0:00 / 0:00")

        self.vocal_volume = _VolumeSlider("Voz")
        self.vocal_volume.changed.connect(self.vocal_volume_changed)
        self.instrumental_volume = _VolumeSlider("Instrumental")
        self.instrumental_volume.changed.connect(self.instrumental_volume_changed)

        transport = QHBoxLayout()
        transport.addWidget(self.play_button)
        transport.addWidget(self.position_slider, 1)
        transport.addWidget(self.time_label)

        volumes = QHBoxLayout()
        volumes.addWidget(self.vocal_volume, 1)
        volumes.addSpacing(24)
        volumes.addWidget(self.instrumental_volume, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.lyrics_note)
        layout.addWidget(self.lyrics_view, 1)
        layout.addLayout(transport)
        layout.addLayout(volumes)

        # Atalhos: espaço = play/pause, setas = voltar/avançar 5 s
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle_requested.emit)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self.seek_relative_requested.emit(-5))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self.seek_relative_requested.emit(5))

    # ------------------------------------------------------------ conteúdo
    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
        self.setWindowTitle(f"Karaokê — {title}")

    def set_lyrics(self, lyrics: Lyrics) -> None:
        self._lyrics = lyrics
        self._current_line = -1
        self.lyrics_view.clear()
        if not lyrics.lines:
            self.lyrics_note.setText("Sem letra para esta música")
        elif not lyrics.synced:
            self.lyrics_note.setText("Letra sem sincronia")
        else:
            self.lyrics_note.setText("")
        self.lyrics_note.setVisible(bool(self.lyrics_note.text()))
        for line in lyrics.lines:
            item = QListWidgetItem(line.text or "♪")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._style_line(item, current=False)
            self.lyrics_view.addItem(item)

    def set_loading(self, loading: bool) -> None:
        self.play_button.setEnabled(not loading)
        self.position_slider.setEnabled(not loading)
        if loading:
            self.time_label.setText("carregando…")

    def show_error(self, message: str) -> None:
        self.lyrics_note.setText(f"Não foi possível abrir o áudio: {message}")
        self.lyrics_note.setVisible(True)

    # -------------------------------------------------------- reprodução
    def set_duration(self, seconds: float) -> None:
        self._duration = seconds
        self.position_slider.setRange(0, int(seconds * 1000))
        self.set_position(0.0)

    def set_position(self, seconds: float) -> None:
        if not self._slider_held:
            self.position_slider.setValue(int(seconds * 1000))
        self.time_label.setText(f"{format_time(seconds)} / {format_time(self._duration)}")

    def set_playing(self, playing: bool) -> None:
        icon = QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))
        self.play_button.setToolTip("Pausar (espaço)" if playing else "Tocar (espaço)")

    def highlight_line(self, index: int) -> None:
        """Destaca o verso atual e o mantém no centro da tela."""
        if index == self._current_line:
            return
        previous = self.lyrics_view.item(self._current_line) if self._current_line >= 0 else None
        if previous is not None:
            self._style_line(previous, current=False)
        self._current_line = index
        item = self.lyrics_view.item(index) if index >= 0 else None
        if item is not None:
            self._style_line(item, current=True)
            self.lyrics_view.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
        elif self.lyrics_view.count():
            self.lyrics_view.scrollToTop()

    def _style_line(self, item: QListWidgetItem, current: bool) -> None:
        font = QFont(self.lyrics_view.font())
        font.setPointSize(self.LINE_FONT_SIZE + (6 if current else 0))
        font.setBold(current)
        item.setFont(font)
        palette = self.lyrics_view.palette()
        if current:
            item.setForeground(palette.highlight())
        elif self._lyrics.synced:
            item.setForeground(QColor(palette.placeholderText().color()))
        else:
            item.setForeground(palette.text())

    # ------------------------------------------------------------ eventos
    def _on_line_clicked(self, item: QListWidgetItem) -> None:
        line = self._lyrics.lines[self.lyrics_view.row(item)]
        if line.time is not None:
            self.seek_requested.emit(line.time)

    def _on_slider_pressed(self) -> None:
        self._slider_held = True

    def _on_slider_released(self) -> None:
        self._slider_held = False
        self.seek_requested.emit(self.position_slider.value() / 1000)

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)
