"""Uma música da biblioteca."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

VOCALS_NAME = "vocais"
INSTRUMENTAL_NAME = "instrumental"


class SongState(Enum):
    NOT_SEPARATED = auto()  # só o áudio original
    QUEUED = auto()         # aguardando a separação
    SEPARATING = auto()     # separação em andamento
    SEPARATED = auto()      # vocais e instrumental prontos
    FAILED = auto()         # a separação deu erro

    @property
    def is_busy(self) -> bool:
        return self in (SongState.QUEUED, SongState.SEPARATING)


def find_stem(folder: Path, name: str) -> Path | None:
    """Arquivo ``<name>.*`` dentro de ``folder``, se existir."""
    matches = sorted(folder.glob(f"{name}.*")) if folder.is_dir() else []
    return matches[0] if matches else None


@dataclass
class Song:
    path: Path
    stems_dir: Path
    state: SongState = SongState.NOT_SEPARATED
    error: str | None = None

    @property
    def title(self) -> str:
        return self.path.stem

    @property
    def vocals_path(self) -> Path | None:
        return find_stem(self.stems_dir, VOCALS_NAME)

    @property
    def instrumental_path(self) -> Path | None:
        return find_stem(self.stems_dir, INSTRUMENTAL_NAME)

    def has_stems_on_disk(self) -> bool:
        return self.vocals_path is not None and self.instrumental_path is not None
