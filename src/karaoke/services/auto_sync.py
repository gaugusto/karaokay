"""Sincronização automática da letra com os vocais separados.

Nos vocais separados de músicas reais quase nunca há silêncio entre os versos
(reverberação, respiração e vazamento preenchem as pausas). Por isso o
alinhamento usa os **ataques** da voz, os instantes em que o volume sobe
de repente, como no começo de cada verso:

1. força de ataque por quadro de 20 ms (subida do volume em dB, normalizada);
2. cada verso da letra vira um "pulso" no instante em que começa;
3. procura o deslocamento (±90 s) e o andamento (±4%) em que os pulsos mais
   coincidem com os ataques (correlação via FFT);
4. a confiança vem do destaque desse pico em relação a todos os outros
   deslocamentos (z-score), e o 2º melhor pico precisa ser bem menor. Com a
   letra da música certa o pico é nítido e único; com a de outra música, não.
   Sem voz distinguível (volume quase constante), nada é tentado. Se não
   passar, nada é aplicado;
5. cada verso é ajustado para o ataque nítido mais próximo (±0,3 s).

Calibração com três músicas reais (vocais separados pelo app): letra certa
z = 8,8 a 12,7; letra de outra música z = 5,1 a 6,6.

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
PULSE_SIGMA = 0.08         # s: largura do "pulso" de cada verso
SNAP_WINDOW = 0.3          # s: ajuste fino máximo de cada verso
PEAK_MIN = 2.0             # força mínima (desvios-padrão) de um ataque "nítido"
MIN_LINE_GAP = 0.25        # s mínimos entre versos consecutivos
MIN_LINES = 4              # versos com texto necessários para tentar
# Confiança: z-score do pico mapeado para 0–1 (z 5 → 0, z 11 → 1)
Z_FLOOR, Z_SPAN = 5.0, 6.0
MIN_CONFIDENCE = 0.40      # z ≈ 7,4
HIGH_CONFIDENCE = 0.70     # z ≈ 9,2
# O 2º melhor pico (a mais de 1 s do melhor) precisa ser bem menor que o 1º.
# Nas músicas reais: letra certa ≤ 0,62; letra de outra música ≥ 0,64.
MAX_SECOND_PEAK = 0.75
MIN_DYNAMIC_RANGE_DB = 10.0  # abaixo disso não há voz distinguível (ex.: só ruído)


@dataclass
class SyncResult:
    offset: float                  # s somados aos tempos (depois da escala)
    scale: float                   # andamento aplicado aos tempos
    confidence: float              # 0–1
    old_times: list[float] = field(default_factory=list)
    new_times: list[float] = field(default_factory=list)
    snapped: int = 0               # versos ajustados individualmente
    peak_z: float = 0.0            # destaque do pico de correlação
    second_peak: float = 1.0       # 2º melhor pico / melhor (menor = mais inequívoco)

    @property
    def ok(self) -> bool:
        return self.confidence >= MIN_CONFIDENCE and self.second_peak <= MAX_SECOND_PEAK

    @property
    def confidence_label(self) -> str:
        if self.confidence >= HIGH_CONFIDENCE:
            return "alta"
        return "média" if self.ok else "baixa"

    @property
    def already_synced(self) -> bool:
        """A letra já estava praticamente no lugar (só ajustes finos)."""
        return abs(self.offset) < 0.3 and abs(self.scale - 1.0) < 1e-6

    def mapping(self) -> dict[float, float]:
        """Tempo antigo -> tempo novo, para reescrever o LRC."""
        return {round(o, 3): n for o, n in zip(self.old_times, self.new_times)}


# ------------------------------------------------------------------ áudio
def onset_strength(samples: np.ndarray, rate: int) -> np.ndarray:
    """Força de ataque da voz por quadro de 20 ms (normalizada: média 0, desvio 1)."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    hop = max(1, int(rate * HOP))
    frames = len(samples) // hop
    if frames < 10:
        return np.zeros(max(frames, 0))
    trimmed = samples[: frames * hop].reshape(frames, hop).astype(np.float64)
    db = 20 * np.log10(np.sqrt(np.mean(trimmed**2, axis=1)) + 1e-9)
    if np.percentile(db, 95) - np.percentile(db, 5) < MIN_DYNAMIC_RANGE_DB:
        return np.zeros(frames)  # volume quase constante: não há voz para alinhar
    db = np.convolve(db, np.ones(3) / 3, mode="same")
    rise = np.zeros_like(db)
    rise[3:] = db[3:] - db[:-3]  # subida em 60 ms
    strength = np.maximum(rise, 0.0)
    std = strength.std()
    if std < 1e-9:
        return np.zeros(frames)
    return (strength - strength.mean()) / std


def load_onset_strength(path: Path) -> np.ndarray:
    import soundfile as sf

    samples, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return onset_strength(samples, rate)


# ------------------------------------------------------------ alinhamento
def _pulses(starts: list[float], scale: float, frames: int) -> np.ndarray:
    train = np.zeros(frames)
    for start in starts:
        i = int(round(start * scale / HOP))
        if 0 <= i < frames:
            train[i] = 1.0
    half = int(3 * PULSE_SIGMA / HOP)
    kernel = np.exp(-0.5 * (np.arange(-half, half + 1) * HOP / PULSE_SIGMA) ** 2)
    return np.convolve(train, kernel, mode="same")


def _correlate(template: np.ndarray, signal: np.ndarray, max_lag: int) -> np.ndarray:
    """score[lag] para lag em [-max_lag, max_lag] (lag>0 = letra atrasa)."""
    n = len(template) + len(signal)
    size = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(signal, size) * np.conj(np.fft.rfft(template, size)), size)
    lags = np.arange(-max_lag, max_lag + 1)
    return corr[lags % size]


def _peaks(strength: np.ndarray) -> np.ndarray:
    """Instantes (s) dos ataques nítidos."""
    s = strength
    is_peak = (s[1:-1] > s[:-2]) & (s[1:-1] >= s[2:]) & (s[1:-1] > PEAK_MIN)
    return (np.nonzero(is_peak)[0] + 1) * HOP


def align(lyrics: Lyrics, strength: np.ndarray) -> SyncResult:
    """Calcula os novos tempos dos versos a partir da força de ataque da voz."""
    old = [line.time for line in lyrics.lines if line.time is not None]
    starts = [line.time for line in lyrics.lines if line.time is not None and line.text.strip()]
    if len(starts) < MIN_LINES or len(strength) == 0 or not np.any(strength):
        return SyncResult(0.0, 1.0, 0.0, old, list(old))

    max_lag = int(MAX_SHIFT / HOP)
    padded = np.pad(strength, (0, max_lag))
    best = None
    for scale in SCALES:
        template = _pulses(starts, float(scale), len(padded))
        scores = _correlate(template, padded, max_lag)
        k = int(np.argmax(scores))
        if best is None or scores[k] > best[0]:
            best = (scores[k], k - max_lag, float(scale), scores)
    value, lag, scale, scores = best
    offset = lag * HOP
    z = float((value - scores.mean()) / (scores.std() + 1e-12))
    confidence = float(np.clip((z - Z_FLOOR) / Z_SPAN, 0.0, 1.0))
    far = np.abs(np.arange(len(scores)) - (lag + max_lag)) > int(1.0 / HOP)
    second = float(scores[far].max() / value) if value > 0 and far.any() else 1.0

    # Ajuste fino: cada verso vai para o ataque nítido mais próximo
    peaks = _peaks(strength)
    new, snapped, previous = [], 0, -np.inf
    for time in old:
        target = time * scale + offset
        if peaks.size:
            nearest = peaks[np.argmin(np.abs(peaks - target))]
            if abs(nearest - target) <= SNAP_WINDOW and nearest >= previous + MIN_LINE_GAP:
                target, snapped = nearest, snapped + 1
        target = max(target, previous + MIN_LINE_GAP, 0.0)
        new.append(round(float(target), 2))
        previous = target
    return SyncResult(offset, scale, confidence, old, new, snapped, z, second)


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
                signal, args = self.finished, (song_path, align(lyrics, load_onset_strength(vocals)))
            except Exception as exc:
                signal, args = self.failed, (song_path, str(exc) or exc.__class__.__name__)
            if not shiboken6.isValid(self):
                return
            try:
                signal.emit(*args)
            except RuntimeError:
                pass

        threading.Thread(target=work, name="sincronia-automatica", daemon=True).start()
