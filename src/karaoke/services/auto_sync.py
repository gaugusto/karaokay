"""Sincronização automática da letra com os vocais separados.

Ideia: no arquivo de vocais só há voz, então dá para saber quando alguém está
cantando. A letra LRC diz quando cada verso começa. O algoritmo:

1. mede a atividade da voz em quadros de 20 ms (volume acima do ruído);
2. monta a atividade "esperada" pela letra (cada verso canta do seu início
   até pouco antes do próximo);
3. procura o deslocamento (±90 s) e a escala de andamento (±4%) que fazem
   as duas baterem melhor (correlação via FFT);
4. ajusta cada verso para o recomeço da voz mais próximo (±1,2 s);
5. calcula uma nota de confiança; abaixo do mínimo, nada é aplicado.

Não usa reconhecimento de fala: só funciona para letras que já têm tempos
(mesmo que errados). Letras sem tempos precisariam de outro método.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shiboken6
from PySide6.QtCore import QObject, Signal

from karaoke.models.lrc import Lyrics

HOP = 0.02                 # s por quadro
MAX_SHIFT = 90.0           # s de deslocamento procurados para cada lado
SCALES = np.round(np.arange(0.96, 1.0401, 0.005), 3)  # andamento (1 = igual)
SNAP_WINDOW = 1.2          # s para procurar o recomeço da voz perto de cada verso
MIN_GAP_BEFORE_ONSET = 0.2  # s de silêncio antes de contar como "recomeço"
MIN_LINE_GAP = 0.25        # s mínimos entre versos consecutivos
MAX_LINE_DURATION = 8.0    # s máximos que um verso "canta" na atividade esperada
MATCH_WINDOW = 0.8         # s: verso "casa" se a voz recomeça até essa distância
# Confiança = menor entre (a) sobreposição voz esperada × ouvida (F1) e
# (b) fração dos versos que casam com um recomeço da voz. Em testes com vocais
# sintéticos, a música certa ficou ≥ 0,67 e a de outra música ≤ 0,46.
MIN_CONFIDENCE = 0.55
HIGH_CONFIDENCE = 0.75


@dataclass
class SyncResult:
    offset: float                  # s somados aos tempos (depois da escala)
    scale: float                   # andamento aplicado aos tempos
    confidence: float              # 0–1 (F1 entre voz esperada e ouvida)
    old_times: list[float] = field(default_factory=list)
    new_times: list[float] = field(default_factory=list)
    snapped: int = 0               # versos ajustados individualmente

    @property
    def ok(self) -> bool:
        return self.confidence >= MIN_CONFIDENCE

    @property
    def confidence_label(self) -> str:
        if self.confidence >= HIGH_CONFIDENCE:
            return "alta"
        return "média" if self.ok else "baixa"

    def mapping(self) -> dict[float, float]:
        """Tempo antigo -> tempo novo, para reescrever o LRC."""
        return {round(o, 3): n for o, n in zip(self.old_times, self.new_times)}


# ------------------------------------------------------------------ áudio
def vocal_activity(samples: np.ndarray, rate: int) -> np.ndarray:
    """Atividade da voz (0–1) por quadro de 20 ms, a partir do áudio dos vocais."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    hop = max(1, int(rate * HOP))
    frames = len(samples) // hop
    if frames == 0:
        return np.zeros(0)
    trimmed = samples[: frames * hop].reshape(frames, hop).astype(np.float64)
    rms = np.sqrt(np.mean(trimmed**2, axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    db = np.convolve(db, np.ones(5) / 5, mode="same")  # suaviza ~100 ms
    floor, loud = np.percentile(db, 10), np.percentile(db, 95)
    if loud - floor < 6:  # praticamente sem variação: não há voz distinguível
        return np.zeros(frames)
    threshold = floor + 0.35 * (loud - floor)
    return np.clip((db - threshold) / (0.3 * (loud - floor)) + 0.5, 0.0, 1.0)


def load_vocal_activity(path: Path) -> np.ndarray:
    import soundfile as sf

    samples, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return vocal_activity(samples, rate)


# ------------------------------------------------------------------ letra
def _sung_lines(lyrics: Lyrics) -> list[tuple[float, float]]:
    """(início, fim) de cada verso com texto, pela própria letra."""
    lines = [line for line in lyrics.lines if line.time is not None]
    spans = []
    for i, line in enumerate(lines):
        if not line.text.strip():
            continue
        nxt = lines[i + 1].time if i + 1 < len(lines) else line.time + 4.0
        end = min(nxt - 0.3, line.time + MAX_LINE_DURATION)
        spans.append((line.time, max(end, line.time + 0.5)))
    return spans


def expected_activity(spans: list[tuple[float, float]], scale: float, frames: int) -> np.ndarray:
    expected = np.zeros(frames)
    for start, end in spans:
        a, b = int(start * scale / HOP), int(end * scale / HOP)
        a, b = max(a, 0), min(b, frames)
        if b > a:
            expected[a:b] = 1.0
    return expected


def _correlate(expected: np.ndarray, observed: np.ndarray, max_lag: int) -> np.ndarray:
    """score[lag] para lag em [-max_lag, max_lag] (lag>0 = letra atrasa)."""
    n = len(expected) + len(observed)
    size = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(observed, size) * np.conj(np.fft.rfft(expected, size)), size)
    lags = np.arange(-max_lag, max_lag + 1)
    return corr[lags % size]


def _f1(expected: np.ndarray, observed: np.ndarray) -> float:
    active = observed > 0.5
    exp = expected > 0.5
    tp = np.sum(active & exp)
    if tp == 0:
        return 0.0
    precision = tp / max(np.sum(exp), 1)
    recall = tp / max(np.sum(active), 1)
    return float(2 * precision * recall / (precision + recall))


def _onsets(observed: np.ndarray) -> np.ndarray:
    """Quadros em que a voz recomeça depois de uma pausa."""
    active = observed > 0.5
    need = int(MIN_GAP_BEFORE_ONSET / HOP)
    onsets = []
    silent = need  # conta o começo do arquivo como silêncio
    for i, on in enumerate(active):
        if on:
            if silent >= need:
                onsets.append(i)
            silent = 0
        else:
            silent += 1
    return np.array(onsets, dtype=float) * HOP


def align(lyrics: Lyrics, observed: np.ndarray) -> SyncResult:
    """Calcula os novos tempos dos versos a partir da atividade da voz."""
    old = [line.time for line in lyrics.lines if line.time is not None]
    spans = _sung_lines(lyrics)
    if not spans or len(observed) == 0 or not observed.any():
        return SyncResult(0.0, 1.0, 0.0, old, list(old))

    centered = observed - observed.mean()
    max_lag = int(MAX_SHIFT / HOP)
    best = (-np.inf, 0, 1.0)
    for scale in SCALES:
        expected = expected_activity(spans, scale, len(observed) + max_lag)
        scores = _correlate(expected, np.pad(centered, (0, max_lag)), max_lag)
        lag = int(np.argmax(scores)) - max_lag
        if scores[lag + max_lag] > best[0]:
            best = (scores[lag + max_lag], lag, float(scale))
    _, lag, scale = best
    offset = lag * HOP

    shifted = [(s * scale + offset, e * scale + offset) for s, e in spans]
    overlap = _f1(expected_activity(shifted, 1.0, len(observed)), observed)
    onsets = _onsets(observed)
    if onsets.size:
        matched = sum(np.min(np.abs(onsets - start)) <= MATCH_WINDOW for start, _ in shifted)
        match_ratio = matched / len(shifted)
    else:
        match_ratio = 0.0
    confidence = float(min(overlap, match_ratio))

    # Ajuste fino: cada verso vai para o recomeço da voz mais próximo
    new, snapped, previous = [], 0, -np.inf
    for time in old:
        target = time * scale + offset
        if onsets.size:
            nearest = onsets[np.argmin(np.abs(onsets - target))]
            if abs(nearest - target) <= SNAP_WINDOW and nearest >= previous + MIN_LINE_GAP:
                target, snapped = nearest, snapped + 1
        target = max(target, previous + MIN_LINE_GAP, 0.0)
        new.append(round(float(target), 2))
        previous = target
    return SyncResult(offset, scale, confidence, old, new, snapped)


# ---------------------------------------------------------------- serviço
class AutoSyncService(QObject):
    """Roda o alinhamento em segundo plano (carregar e medir os vocais leva
    alguns segundos)."""

    finished = Signal(str, object)  # caminho da música, SyncResult
    failed = Signal(str, str)

    def run(self, song_path: str | Path, vocals: Path, lyrics: Lyrics) -> None:
        song_path = str(song_path)

        def work() -> None:
            try:
                signal, args = self.finished, (song_path, align(lyrics, load_vocal_activity(vocals)))
            except Exception as exc:
                signal, args = self.failed, (song_path, str(exc) or exc.__class__.__name__)
            if not shiboken6.isValid(self):
                return
            try:
                signal.emit(*args)
            except RuntimeError:
                pass

        threading.Thread(target=work, name="sincronia-automatica", daemon=True).start()
