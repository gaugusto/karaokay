"""Estado da letra de uma música e verificação de sincronia."""

from __future__ import annotations

import re
from enum import Enum, auto
from pathlib import Path

SYNCED_EXT = ".lrc"  # letra sincronizada (formato LRC, com tempos)
PLAIN_EXT = ".txt"   # letra sem tempos

# [mm:ss], [mm:ss.xx] ou [mm:ss:xx] no início da linha
_TIMESTAMP = re.compile(r"^\s*\[(\d{1,3}):([0-5]\d)(?:[.:](\d{1,3}))?\]")


class LyricsState(Enum):
    UNKNOWN = auto()       # ainda não buscada
    SEARCHING = auto()     # buscando no LRCLIB
    SYNCED = auto()        # letra sincronizada (.lrc)
    PLAIN = auto()         # letra sem sincronia (.txt)
    INSTRUMENTAL = auto()  # o LRCLIB marca a música como instrumental
    NOT_FOUND = auto()     # não encontrada
    FAILED = auto()        # erro na busca (rede, API…)


def is_synced_lrc(text: str | None) -> bool:
    """True se o texto é uma letra sincronizada de verdade.

    Exige que a maior parte das linhas com conteúdo comece com um tempo
    [mm:ss.xx] e que haja pelo menos três tempos diferentes; assim um .lrc
    com tudo em 00:00 ou só com cabeçalho não conta como sincronizado.
    """
    if not text:
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    stamps = []
    for line in lines:
        match = _TIMESTAMP.match(line)
        if match:
            minutes, seconds, fraction = match.groups()
            stamps.append(int(minutes) * 60 + int(seconds) + float(f"0.{fraction or 0}"))
    return len(set(stamps)) >= 3 and len(stamps) >= len(lines) / 2


def lyrics_state_on_disk(base: Path) -> tuple[LyricsState, Path | None]:
    """Estado da letra salva em ``base.lrc`` ou ``base.txt``."""
    synced = base.with_name(base.name + SYNCED_EXT)
    plain = base.with_name(base.name + PLAIN_EXT)
    if synced.is_file():
        text = synced.read_text(encoding="utf-8", errors="replace")
        return (LyricsState.SYNCED if is_synced_lrc(text) else LyricsState.PLAIN), synced
    if plain.is_file():
        return LyricsState.PLAIN, plain
    return LyricsState.UNKNOWN, None
