"""Janela do player: letra sincronizada, play/pause e volumes."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProxyStyle,
    QPushButton,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from karaoke.models.lrc import Lyrics
from karaoke.views import dialogs

DEFAULT_VOCAL_VOLUME = 30         # %
DEFAULT_INSTRUMENTAL_VOLUME = 100  # %
SCROLL_ANIMATION_MS = 350


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class _JumpToClickStyle(QProxyStyle):
    """Clique com o botão esquerdo leva a barra direto ao ponto clicado
    (em vez de avançar um passo) e continua permitindo arrastar."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_Slider_AbsoluteSetButtons:
            return Qt.MouseButton.LeftButton.value
        return super().styleHint(hint, option, widget, returnData)


class JumpSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None) -> None:
        super().__init__(orientation, parent)
        self._jump_style = _JumpToClickStyle()  # mantém a referência viva
        self.setStyle(self._jump_style)


class _VolumeSlider(QWidget):
    changed = Signal(float)  # 0.0 – 1.0

    def __init__(self, label: str, value: int = 100, parent=None) -> None:
        super().__init__(parent)
        self.slider = JumpSlider(Qt.Orientation.Horizontal)
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

    @property
    def volume(self) -> float:
        return self.slider.value() / 100

    def _on_changed(self, value: int) -> None:
        self.value_label.setText(f"{value}%")
        self.changed.emit(value / 100)


class LyricsView(QListWidget):
    """Letra com o verso atual sempre no meio da área visível.

    Um espaço vazio de meia altura antes do primeiro e depois do último verso
    permite centralizar qualquer verso; a rolagem até o próximo é animada, e a
    letra vai subindo conforme os versos passam.
    """

    line_clicked = Signal(int)  # índice do verso

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWordWrap(True)
        self.setSpacing(4)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._top = self._bottom = None
        self._centered = 0
        self._animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._animation.setDuration(SCROLL_ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.itemClicked.connect(self._on_item_clicked)

    # ------------------------------------------------------------ conteúdo
    def set_lines(self, texts: list[str]) -> None:
        self._animation.stop()
        self.clear()
        self._top = self._spacer()
        for text in texts:
            item = QListWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.addItem(item)
        self._bottom = self._spacer()
        self._update_spacers()
        self._centered = 0
        self.center_on(0, animate=False)

    def line_count(self) -> int:
        return max(0, self.count() - 2)

    def line_item(self, index: int) -> QListWidgetItem | None:
        if 0 <= index < self.line_count():
            return self.item(index + 1)
        return None

    # ------------------------------------------------------------ rolagem
    def center_on(self, index: int, animate: bool = True) -> None:
        """Rola para deixar o verso ``index`` no meio da área visível."""
        item = self.line_item(max(index, 0))
        if item is None:
            return
        self._centered = max(index, 0)
        self.doItemsLayout()  # mede o verso com a fonte atual (destacado é maior)
        bar = self.verticalScrollBar()
        rect = self.visualItemRect(item)
        target = bar.value() + rect.center().y() - self.viewport().height() // 2
        target = max(bar.minimum(), min(bar.maximum(), target))
        self._animation.stop()
        if animate and self.isVisible():
            self._animation.setStartValue(bar.value())
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            bar.setValue(target)

    def _spacer(self) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(item)
        return item

    def _update_spacers(self) -> None:
        half = max(0, self.viewport().height() // 2)
        for item in (self._top, self._bottom):
            if item is not None:
                item.setSizeHint(QSize(1, half))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_spacers()
        self.center_on(self._centered, animate=False)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        row = self.row(item) - 1
        if 0 <= row < self.line_count():
            self.line_clicked.emit(row)


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
        self._playing = False
        self._ask_before_closing = True

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

        self.lyrics_view = LyricsView()
        self.lyrics_view.line_clicked.connect(self._on_line_clicked)

        # Controles
        self.play_button = QPushButton()
        self.play_button.setFixedWidth(48)
        self.play_button.clicked.connect(self.toggle_requested)
        self.set_playing(False)

        self.position_slider = JumpSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.time_label = QLabel("0:00 / 0:00")

        self.vocal_volume = _VolumeSlider("Voz", DEFAULT_VOCAL_VOLUME)
        self.vocal_volume.changed.connect(self.vocal_volume_changed)
        self.instrumental_volume = _VolumeSlider("Instrumental", DEFAULT_INSTRUMENTAL_VOLUME)
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
        if not lyrics.lines:
            self.lyrics_note.setText("Sem letra para esta música")
        elif not lyrics.synced:
            self.lyrics_note.setText("Letra sem sincronia")
        else:
            self.lyrics_note.setText("")
        self.lyrics_note.setVisible(bool(self.lyrics_note.text()))
        self.lyrics_view.set_lines([line.text or "♪" for line in lyrics.lines])
        for i in range(self.lyrics_view.line_count()):
            self._style_line(self.lyrics_view.line_item(i), current=False)
        self.lyrics_view.center_on(0, animate=False)

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

    @property
    def is_playing(self) -> bool:
        return self._playing

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        icon = QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay
        self.play_button.setIcon(self.style().standardIcon(icon))
        self.play_button.setToolTip("Pausar (espaço)" if playing else "Tocar (espaço)")

    def highlight_line(self, index: int) -> None:
        """Destaca o verso atual e o leva, com animação, ao meio da tela.

        Antes do primeiro verso, o primeiro fica no meio, ainda sem destaque.
        """
        if index == self._current_line:
            return
        previous = self.lyrics_view.line_item(self._current_line)
        if previous is not None:
            self._style_line(previous, current=False)
        self._current_line = index
        item = self.lyrics_view.line_item(index)
        if item is not None:
            self._style_line(item, current=True)
        self.lyrics_view.center_on(max(index, 0))

    def _style_line(self, item: QListWidgetItem | None, current: bool) -> None:
        if item is None:
            return
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
    def _on_line_clicked(self, index: int) -> None:
        line = self._lyrics.lines[index]
        if line.time is not None:
            self.seek_requested.emit(line.time)

    def _on_slider_pressed(self) -> None:
        self._slider_held = True

    def _on_slider_released(self) -> None:
        self._slider_held = False
        self.seek_requested.emit(self.position_slider.value() / 1000)

    def close_without_asking(self) -> None:
        """Fecha sem confirmação (quem chamou já confirmou ou decidiu)."""
        self._ask_before_closing = False
        self.close()

    def closeEvent(self, event) -> None:
        if self._playing and self._ask_before_closing and not dialogs.confirm(
            self, "Fechar o player", "Uma música está tocando. Deseja fechar o player?"
        ):
            event.ignore()
            return
        self._ask_before_closing = False
        self.closed.emit()
        super().closeEvent(event)
