"""Uma música da biblioteca."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from karaoke.models.lyrics import LyricsState, lyrics_state_on_disk

VOCALS_NAME = "vocais"
INSTRUMENTAL_NAME = "instrumental"


class SongState(Enum):
    NOT_SEPARATED = auto()  # só o áudio original, ainda fora da fila
    QUEUED = auto()         # na fila, aguardando a vez
    SEPARATING = auto()     # sendo processada agora
    SEPARATED = auto()      # vocais e instrumental prontos (processada)
    FAILED = auto()         # a separação deu erro

    @property
    def is_busy(self) -> bool:
        return self in (SongState.QUEUED, SongState.SEPARATING)


class SeparationMethod(str, Enum):
    """Como os vocais são separados: no computador ou na nuvem (MVSEP)."""

    LOCAL = "local"  # BS-RoFormer rodando aqui (audio-separator)
    MVSEP = "mvsep"  # API do mvsep.com

    @property
    def label(self) -> str:
        return "Local (BS-RoFormer)" if self is SeparationMethod.LOCAL else "MVSEP (nuvem)"

    @classmethod
    def parse(cls, value) -> "SeparationMethod":
        """Valor salvo (texto) → método; qualquer coisa desconhecida é local."""
        try:
            return cls(value)
        except ValueError:
            return cls.LOCAL


# Chave dos metadados (músicas/.metadados/<nome>.json) com o método escolhido
METHOD_KEY = "separation_method"


def read_separation_method(metadata_path: Path | None) -> SeparationMethod:
    """Método escolhido ao adicionar a música; sem registro, local."""
    if metadata_path is None:
        return SeparationMethod.LOCAL
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SeparationMethod.LOCAL
    return SeparationMethod.parse(data.get(METHOD_KEY) if isinstance(data, dict) else None)


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
    lyrics_base: Path | None = None    # letras/<nome do áudio> (sem extensão)
    metadata_path: Path | None = None  # metadados do YouTube salvos no download
    added_at: float = 0.0              # quando o arquivo chegou à pasta (mtime)
    queue_position: int | None = None  # ordem de entrada na fila de processamento
    progress: int | None = None        # porcentagem do processamento em andamento
    lyrics_state: LyricsState = LyricsState.UNKNOWN
    lyrics_error: str | None = None

    @property
    def title(self) -> str:
        return self.path.stem

    @property
    def separation_method(self) -> SeparationMethod:
        return read_separation_method(self.metadata_path)

    @property
    def vocals_path(self) -> Path | None:
        return find_stem(self.stems_dir, VOCALS_NAME)

    @property
    def instrumental_path(self) -> Path | None:
        return find_stem(self.stems_dir, INSTRUMENTAL_NAME)

    def has_stems_on_disk(self) -> bool:
        return self.vocals_path is not None and self.instrumental_path is not None

    def related_paths(self) -> list[Path]:
        """Todos os arquivos e pastas da música que existem no disco:
        áudio, vocais/instrumental separados, letra (.lrc/.txt) e metadados."""
        candidates = [self.path, self.stems_dir, self.metadata_path]
        if self.lyrics_base is not None:
            candidates += [
                self.lyrics_base.with_name(self.lyrics_base.name + ext) for ext in (".lrc", ".txt")
            ]
        return [p for p in candidates if p is not None and (p.exists() or p.is_symlink())]

    @property
    def lyrics_path(self) -> Path | None:
        if self.lyrics_base is None:
            return None
        return lyrics_state_on_disk(self.lyrics_base)[1]

    def lyrics_state_on_disk(self) -> LyricsState:
        if self.lyrics_base is None:
            return LyricsState.UNKNOWN
        return lyrics_state_on_disk(self.lyrics_base)[0]
