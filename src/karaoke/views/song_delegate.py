"""Desenho de cada música nas listas, em forma de cartão."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from karaoke.models import LyricsState, MusicLibraryModel, Song, SongState
from karaoke.views.icons import icon_pixmap
from karaoke.views.theme import Colors, color

STATE_TOOLTIPS = {
    SongState.NOT_SEPARATED: "Aguardando entrar na fila",
    SongState.QUEUED: "Na fila, aguardando a vez",
    SongState.SEPARATING: "Separando vocais e instrumental…",
    SongState.SEPARATED: "Vocais e instrumental separados",
    SongState.FAILED: "Falha no processamento",
}

LYRICS_LABELS = {
    LyricsState.UNKNOWN: "",
    LyricsState.SEARCHING: "buscando letra…",
    LyricsState.SYNCED: "letra sincronizada",
    LyricsState.PLAIN: "letra sem sincronia",
    LyricsState.INSTRUMENTAL: "instrumental",
    LyricsState.NOT_FOUND: "sem letra",
    LyricsState.FAILED: "erro ao buscar letra",
}

# Etiqueta (texto, cor) de cada situação
_LYRICS_BADGES = {
    LyricsState.UNKNOWN: ("sem letra", Colors.TEXT_MUTED),
    LyricsState.SEARCHING: ("buscando letra…", Colors.INFO),
    LyricsState.SYNCED: ("letra sincronizada", Colors.SUCCESS),
    LyricsState.PLAIN: ("letra sem sincronia", Colors.WARNING),
    LyricsState.INSTRUMENTAL: ("instrumental", Colors.TEXT_SECONDARY),
    LyricsState.NOT_FOUND: ("sem letra", Colors.TEXT_SECONDARY),
    LyricsState.FAILED: ("erro na letra", Colors.DANGER),
}


@dataclass(frozen=True)
class RowAction:
    """Um ícone clicável à direita do cartão."""

    key: str          # "play", "search", "delete"
    tooltip: str      # descrição que aparece ao passar o mouse
    enabled: bool = True
    shortcut: str = ""  # atalho com a música selecionada (ex.: "Ctrl+S")
    danger: bool = False  # destaca em vermelho ao passar o mouse

    @property
    def icon(self) -> str:
        return self.key

    @property
    def full_tooltip(self) -> str:
        return f"{self.tooltip} ({self.shortcut})" if self.shortcut else self.tooltip

    def matches(self, sequence: QKeySequence) -> bool:
        return bool(self.shortcut) and QKeySequence(self.shortcut) == sequence


def pending_actions(song: Song) -> list[RowAction]:
    return [RowAction("delete", "Excluir", shortcut="Delete", danger=True)]


def processed_actions(song: Song) -> list[RowAction]:
    return [
        RowAction("play", "Abrir no player", shortcut="Enter"),
        RowAction("search", "Buscar letra manualmente", shortcut="Ctrl+B"),
        RowAction("delete", "Excluir", shortcut="Delete", danger=True),
    ]


def pending_badge(song: Song) -> tuple[str, str]:
    """Etiqueta de uma música na lista "A processar"."""
    if song.state is SongState.SEPARATING:
        progress = f" {song.progress}%" if song.progress is not None else "…"
        return f"processando{progress}", Colors.ACCENT
    if song.state is SongState.FAILED:
        return "falha", Colors.DANGER
    return "aguardando", Colors.TEXT_SECONDARY


def processed_badge(song: Song) -> tuple[str, str]:
    """Etiqueta de uma música na lista "Processadas"."""
    return _LYRICS_BADGES[song.lyrics_state]


def queue_position(song: Song, row: int) -> int | None:
    """Número mostrado no círculo da fila (só para quem está na fila)."""
    return row + 1 if song.state in (SongState.QUEUED, SongState.SEPARATING) else None


class _CardDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 58
    GAP = 6
    RADIUS = 12
    BUTTON = 34      # área clicável de cada ícone
    ICON = 18
    BUTTON_GAP = 2
    RIGHT_MARGIN = 10

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Definidos pela lista: ícone sob o mouse e ícone pressionado, (linha, chave)
        self.hovered_action: tuple[int, str] | None = None
        self.pressed_action: tuple[int, str] | None = None

    def actions(self, song: Song) -> list[RowAction]:
        return []

    def card_rect(self, rect) -> QRectF:
        return QRectF(rect).adjusted(2, self.GAP / 2, -2, -self.GAP / 2)

    def action_rects(self, rect, song: Song) -> list[tuple[RowAction, QRectF]]:
        """Ícones da direita para a esquerda, alinhados à direita do cartão."""
        card = self.card_rect(rect)
        actions = self.actions(song)
        result = []
        right = card.right() - self.RIGHT_MARGIN
        top = card.center().y() - self.BUTTON / 2
        for action in reversed(actions):
            box = QRectF(right - self.BUTTON, top, self.BUTTON, self.BUTTON)
            result.append((action, box))
            right = box.left() - self.BUTTON_GAP
        result.reverse()
        return result

    def action_at(self, rect, song: Song | None, pos) -> RowAction | None:
        if song is None:
            return None
        point = QPointF(pos)
        for action, box in self.action_rects(rect, song):
            if box.contains(point):
                return action
        return None

    def _paint_actions(self, painter: QPainter, option, index, song: Song) -> float:
        """Desenha os ícones e devolve onde eles começam (x)."""
        boxes = self.action_rects(option.rect, song)
        if not boxes:
            return self.card_rect(option.rect).right()
        ratio = painter.device().devicePixelRatioF() if painter.device() else 1.0
        row = index.row()
        for action, box in boxes:
            hovered = self.hovered_action == (row, action.key) and action.enabled
            pressed = self.pressed_action == (row, action.key) and action.enabled
            if hovered or pressed:
                painter.setPen(Qt.PenStyle.NoPen)
                if action.danger:
                    painter.setBrush(color(Colors.DANGER, 70 if pressed else 40))
                else:
                    painter.setBrush(color(Colors.ACCENT_DIM if pressed else Colors.BORDER_STRONG))
                painter.drawRoundedRect(box, 9, 9)
            if not action.enabled:
                tint = Colors.TEXT_MUTED
            elif hovered or pressed:
                tint = Colors.DANGER if action.danger else Colors.TEXT
            else:
                tint = Colors.TEXT_SECONDARY
            icon = icon_pixmap(action.icon, tint, self.ICON, ratio)
            offset = (self.BUTTON - self.ICON) / 2
            if not action.enabled:
                painter.setOpacity(0.55)
            painter.drawPixmap(QPointF(box.left() + offset, box.top() + offset), icon)
            painter.setOpacity(1.0)
        return boxes[0][1].left()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), self.ROW_HEIGHT + self.GAP)

    # Subclasses definem o conteúdo
    def badge(self, song: Song) -> tuple[str, str]:
        raise NotImplementedError

    def leading(self, song: Song, row: int) -> int | None:
        return None

    def title_color(self, song: Song) -> str:
        return Colors.TEXT

    def emphasized(self, song: Song) -> bool:
        return False

    def progress(self, song: Song) -> int | None:
        return None

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        song: Song | None = index.data(MusicLibraryModel.SongRole)
        if song is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self.card_rect(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)

        # Fundo do cartão
        path = QPainterPath()
        path.addRoundedRect(card, self.RADIUS, self.RADIUS)
        background = Colors.SURFACE_SELECTED if selected else Colors.SURFACE_HOVER if hovered else Colors.SURFACE
        painter.fillPath(path, color(background))
        if focused:  # item atual com a lista em foco (navegação por teclado)
            painter.setPen(QPen(color(Colors.ACCENT_HOVER), 2))
        else:
            painter.setPen(color(Colors.ACCENT if selected else Colors.BORDER))
        painter.drawPath(path)

        x = card.left() + 16
        center_y = card.center().y()

        # Círculo com a posição na fila
        number = self.leading(song, index.row())
        if number is not None:
            circle = QRectF(x, center_y - 15, 30, 30)
            active = song.state is SongState.SEPARATING
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color(Colors.ACCENT if active else Colors.SURFACE_RAISED))
            painter.drawEllipse(circle)
            painter.setPen(color(Colors.ON_ACCENT if active else Colors.TEXT_SECONDARY))
            small = QFont(option.font)
            small.setBold(True)
            painter.setFont(small)
            painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, str(number))
            x = circle.right() + 14

        # Ícones de ação, bem à direita
        actions_left = self._paint_actions(painter, option, index, song)
        badge_right = actions_left - 12 if actions_left < card.right() else card.right() - 14

        # Etiqueta à direita (antes dos ícones)
        text, badge_color = self.badge(song)
        badge_font = QFont(option.font)
        badge_font.setPointSizeF(option.font.pointSizeF() * 0.85)
        badge_font.setBold(True)
        metrics = QFontMetrics(badge_font)
        badge_w = metrics.horizontalAdvance(text) + 22
        badge = QRectF(badge_right - badge_w, center_y - 13, badge_w, 26)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color(badge_color, 40))
        painter.drawRoundedRect(badge, 13, 13)
        painter.setPen(color(badge_color))
        painter.setFont(badge_font)
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)

        # Título (cortado com "…" se não couber)
        title_font = QFont(option.font)
        title_font.setPointSizeF(option.font.pointSizeF() * 1.05)
        title_font.setWeight(QFont.Weight.Bold if self.emphasized(song) else QFont.Weight.Medium)
        painter.setFont(title_font)
        painter.setPen(color(self.title_color(song)))
        title_rect = QRectF(x, card.top(), badge.left() - 14 - x, card.height())
        elided = QFontMetrics(title_font).elidedText(
            song.title, Qt.TextElideMode.ElideRight, int(title_rect.width())
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

        # Barra de progresso fina na base do cartão
        percent = self.progress(song)
        if percent is not None:
            track = QRectF(card.left() + 16, card.bottom() - 9, badge.right() - card.left() - 16, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color(Colors.BORDER_STRONG))
            painter.drawRoundedRect(track, 2, 2)
            done = QRectF(track.left(), track.top(), track.width() * percent / 100, track.height())
            painter.setBrush(color(Colors.ACCENT))
            painter.drawRoundedRect(done, 2, 2)

        painter.restore()


class PendingSongDelegate(_CardDelegate):
    """Lista "A processar": posição na fila, nome e situação."""

    def badge(self, song: Song) -> tuple[str, str]:
        return pending_badge(song)

    def actions(self, song: Song) -> list[RowAction]:
        return pending_actions(song)

    def leading(self, song: Song, row: int) -> int | None:
        return queue_position(song, row)

    def emphasized(self, song: Song) -> bool:
        return song.state is SongState.SEPARATING

    def title_color(self, song: Song) -> str:
        return Colors.TEXT_SECONDARY if song.state is SongState.FAILED else Colors.TEXT

    def progress(self, song: Song) -> int | None:
        if song.state is SongState.SEPARATING:
            return song.progress or 0
        return None


class ProcessedSongDelegate(_CardDelegate):
    """Lista "Processadas": nome e situação da letra."""

    def badge(self, song: Song) -> tuple[str, str]:
        return processed_badge(song)

    def actions(self, song: Song) -> list[RowAction]:
        return processed_actions(song)


def song_tooltip(index: QModelIndex | QPersistentModelIndex) -> str:
    song = index.data(MusicLibraryModel.SongRole)
    if song is None:
        return ""
    text = f"{song.path.name}\n{STATE_TOOLTIPS[song.state]}"
    if song.state is SongState.FAILED and song.error:
        text += f": {song.error}"
    if song.state is SongState.SEPARATED:
        lyrics = LYRICS_LABELS.get(song.lyrics_state) or "ainda não baixada (a busca abre ao tocar)"
        text += f"\nLetra: {lyrics}"
        if song.lyrics_state is LyricsState.FAILED and song.lyrics_error:
            text += f" ({song.lyrics_error})"
        if song.lyrics_path:
            text += f"\n{song.lyrics_path.name}"
    return text
