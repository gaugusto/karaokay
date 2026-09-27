"""Lista das músicas guardadas na pasta de músicas."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from karaoke.paths import AUDIO_EXTENSIONS


class MusicLibrary(QListWidget):
    """Mostra todos os arquivos de áudio da pasta e se atualiza sozinha."""

    PATH_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, folder: Path, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder
        self._folder.mkdir(parents=True, exist_ok=True)
        self.setAlternatingRowColors(True)

        self._watcher = QFileSystemWatcher([str(self._folder)], self)
        self._watcher.directoryChanged.connect(self.refresh)
        self.refresh()

    def songs(self) -> list[Path]:
        return sorted(
            (
                p
                for p in self._folder.iterdir()
                if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
            ),
            key=lambda p: p.stem.casefold(),
        )

    def refresh(self) -> None:
        current = self.currentItem()
        selected = current.data(self.PATH_ROLE) if current else None

        self.clear()
        for path in self.songs():
            item = QListWidgetItem(path.stem)
            item.setData(self.PATH_ROLE, str(path))
            item.setToolTip(path.name)
            self.addItem(item)
            if str(path) == selected:
                self.setCurrentItem(item)

    def select_path(self, path: str) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(self.PATH_ROLE) == path:
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return
