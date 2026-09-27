"""Lista das músicas guardadas na pasta de músicas."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from karaoke.paths import AUDIO_EXTENSIONS
from karaoke.separator import is_separated


class MusicLibrary(QListWidget):
    """Mostra todos os arquivos de áudio da pasta e se atualiza sozinha.

    Músicas ainda sem vocais separados aparecem em cinza; as que estão sendo
    processadas mostram o estado ao lado do nome.
    """

    PATH_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, folder: Path, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder
        self._folder.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, str] = {}
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

    def set_state(self, path: str, state: str | None) -> None:
        """Define (ou limpa, com None) um estado exibido ao lado da música."""
        if state:
            self._states[path] = state
        else:
            self._states.pop(path, None)
        self.refresh()

    def refresh(self) -> None:
        current = self.currentItem()
        selected = current.data(self.PATH_ROLE) if current else None
        dim = self.palette().color(QPalette.ColorRole.PlaceholderText)

        self.clear()
        for path in self.songs():
            key = str(path)
            state = self._states.get(key)
            item = QListWidgetItem(f"{path.stem}   — {state}" if state else path.stem)
            item.setData(self.PATH_ROLE, key)
            if is_separated(path):
                item.setToolTip(f"{path.name}\nVocais separados")
            else:
                item.setForeground(dim)
                item.setToolTip(f"{path.name}\nVocais ainda não separados")
            self.addItem(item)
            if key == selected:
                self.setCurrentItem(item)

    def select_path(self, path: str) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(self.PATH_ROLE) == path:
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return
