"""Leitura de letras LRC: cada verso com o tempo em que começa."""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from pathlib import Path

from karaoke.models.lyrics import SYNCED_EXT, is_synced_lrc

_TIMESTAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_OFFSET = re.compile(r"^\s*\[offset:\s*([+-]?\d+)\s*\]", re.IGNORECASE)


@dataclass(frozen=True)
class LyricLine:
    time: float | None  # segundos; None em letras sem sincronia
    text: str


@dataclass(frozen=True)
class Lyrics:
    lines: tuple[LyricLine, ...] = ()
    synced: bool = False
    offset: float = 0.0  # segundos da tag [offset:] já aplicados aos tempos

    def first_sung_line(self) -> int:
        """Índice do primeiro verso com texto (pula linhas vazias/instrumentais)."""
        for index, line in enumerate(self.lines):
            if line.text.strip():
                return index
        return 0 if self.lines else -1

    def line_at(self, seconds: float) -> int:
        """Índice do verso que está sendo cantado em ``seconds`` (-1 antes do 1º)."""
        if not self.synced or not self.lines:
            return -1
        times = [line.time for line in self.lines]
        return bisect.bisect_right(times, seconds) - 1


def _seconds(minutes: str, seconds: str, fraction: str | None) -> float:
    frac = float(f"0.{fraction}") if fraction else 0.0
    return int(minutes) * 60 + int(seconds) + frac


def parse_lrc(text: str) -> Lyrics:
    """Converte um texto LRC em versos ordenados pelo tempo.

    Aceita vários tempos na mesma linha ([00:10.00][01:20.00]refrão) e a
    tag [offset:ms] (positivo adianta a letra), onde quer que ela esteja.
    """
    offset = 0.0
    for raw in text.splitlines():
        match = _OFFSET.match(raw)
        if match:
            offset = int(match.group(1)) / 1000
    lines: list[LyricLine] = []
    for raw in text.splitlines():
        if _OFFSET.match(raw):
            continue
        rest = raw.strip()
        stamps = []
        while (match := _TIMESTAMP.match(rest)) is not None:
            stamps.append(_seconds(*match.groups()))
            rest = rest[match.end():].lstrip()
        for stamp in stamps:
            lines.append(LyricLine(max(0.0, stamp - offset), rest))
    lines.sort(key=lambda line: line.time)
    return Lyrics(tuple(lines), synced=bool(lines), offset=offset)


def write_lrc_offset(path: Path, offset: float) -> None:
    """Grava a tag [offset:ms] no .lrc (substitui a anterior).

    Pela convenção do LRC, o tempo exibido é ``tempo_do_verso - offset``:
    um offset positivo adianta a letra, negativo atrasa.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line for line in text.splitlines() if not _OFFSET.match(line)]
    ms = round(offset * 1000)
    if ms:
        lines.insert(0, f"[offset:{ms:+d}]")
    temp = path.with_name(path.name + ".tmp")
    temp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    temp.replace(path)


def plain_lyrics(text: str) -> Lyrics:
    return Lyrics(tuple(LyricLine(None, line.strip()) for line in text.strip().splitlines()))


def load_lyrics(path: Path | None) -> Lyrics:
    """Lê letras/<nome>.lrc ou .txt; sem arquivo, devolve uma letra vazia."""
    if path is None or not path.is_file():
        return Lyrics()
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == SYNCED_EXT and is_synced_lrc(text):
        return parse_lrc(text)
    return plain_lyrics(_TIMESTAMP.sub("", text))


def _format_stamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    return f"[{minutes:02d}:{seconds - minutes * 60:05.2f}]"


def retime_lrc(text: str, mapping: dict[float, float]) -> str:
    """Reescreve os tempos de um LRC.

    ``mapping`` leva o tempo efetivo de cada verso (já com a tag [offset]
    aplicada, arredondado a 3 casas) ao tempo novo. A tag [offset] sai, pois
    o ajuste passa a estar nos próprios tempos; cabeçalhos como [ar:] ficam.
    """
    offset = 0.0
    for raw in text.splitlines():
        match = _OFFSET.match(raw)
        if match:
            offset = int(match.group(1)) / 1000
    out = []
    for raw in text.splitlines():
        if _OFFSET.match(raw):
            continue
        rest = raw.strip()
        stamps = []
        while (match := _TIMESTAMP.match(rest)) is not None:
            stamps.append(max(0.0, _seconds(*match.groups()) - offset))
            rest = rest[match.end():].lstrip()
        if not stamps:
            out.append(raw)
            continue
        prefix = "".join(_format_stamp(mapping.get(round(t, 3), t)) for t in stamps)
        out.append(prefix + rest)
    return "\n".join(out).rstrip() + "\n"
