"""Desenho de cada música nas listas, em forma de cartão."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from karaoke.models import LyricsState, MusicLibraryModel, Song, SongState
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
    LyricsState.UNKNOWN: ("letra pendente", Colors.TEXT_MUTED),
    LyricsState.SEARCHING: ("buscando letra…", Colors.INFO),
    LyricsState.SYNCED: ("letra sincronizada", Colors.SUCCESS),
    LyricsState.PLAIN: ("letra sem sincronia", Colors.WARNING),
    LyricsState.INSTRUMENTAL: ("instrumental", Colors.TEXT_SECONDARY),
    LyricsState.NOT_FOUND: ("sem letra", Colors.TEXT_SECONDARY),
    LyricsState.FAILED: ("erro na letra", Colors.DANGER),
}


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
        card = QRectF(option.rect).adjusted(2, self.GAP / 2, -2, -self.GAP / 2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Fundo do cartão
        path = QPainterPath()
        path.addRoundedRect(card, self.RADIUS, self.RADIUS)
        background = Colors.SURFACE_SELECTED if selected else Colors.SURFACE_HOVER if hovered else Colors.SURFACE
        painter.fillPath(path, color(background))
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
            painter.setPen(color("#FFFFFF" if active else Colors.TEXT_SECONDARY))
            small = QFont(option.font)
            small.setBold(True)
            painter.setFont(small)
            painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, str(number))
            x = circle.right() + 14

        # Etiqueta à direita
        text, badge_color = self.badge(song)
        badge_font = QFont(option.font)
        badge_font.setPointSizeF(option.font.pointSizeF() * 0.85)
        badge_font.setBold(True)
        metrics = QFontMetrics(badge_font)
        badge_w = metrics.horizontalAdvance(text) + 22
        badge = QRectF(card.right() - 14 - badge_w, center_y - 13, badge_w, 26)
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
            track = QRectF(card.left() + 16, card.bottom() - 9, card.width() - 32, 4)
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


def song_tooltip(index: QModelIndex | QPersistentModelIndex) -> str:
    song = index.data(MusicLibraryModel.SongRole)
    if song is None:
        return ""
    text = f"{song.path.name}\n{STATE_TOOLTIPS[song.state]}"
    if song.state is SongState.FAILED and song.error:
        text += f": {song.error}"
    if song.state is SongState.SEPARATED:
        lyrics = LYRICS_LABELS.get(song.lyrics_state) or "letra ainda não buscada"
        text += f"\nLetra: {lyrics}"
        if song.lyrics_state is LyricsState.FAILED and song.lyrics_error:
            text += f" ({song.lyrics_error})"
        if song.lyrics_path:
            text += f"\n{song.lyrics_path.name}"
    return text
