"""Tocador de vocais + instrumental com volumes independentes.

Os dois arquivos são carregados na memória e misturados pelo próprio app,
amostra por amostra, antes de ir para a placa de som. Assim eles nunca
se dessincronizam e o volume da voz muda na hora.
"""

from __future__ import annotations

import threading
from enum import Enum, auto
from pathlib import Path

import numpy as np
import shiboken6
from PySide6.QtCore import QIODevice, QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices

CHANNELS = 2
BYTES_PER_FRAME = CHANNELS * 2  # int16 estéreo
BUFFER_SECONDS = 0.12           # latência: volume/seek respondem em ~0,1 s


class PlayerState(Enum):
    STOPPED = auto()
    PLAYING = auto()
    PAUSED = auto()


def load_stem(path: Path) -> tuple[np.ndarray, int]:
    """Lê um arquivo de áudio como float32 (quadros × 2 canais)."""
    import soundfile as sf

    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    return np.ascontiguousarray(data[:, :2]), rate


def has_audio_output() -> bool:
    return not QMediaDevices.defaultAudioOutput().isNull()


def mix(vocals: np.ndarray, instrumental: np.ndarray, vocal_gain: float, inst_gain: float) -> bytes:
    """Mistura dois trechos float32 e converte para PCM int16."""
    return mix_with_level(vocals, instrumental, vocal_gain, inst_gain)[0]


def mix_with_level(
    vocals: np.ndarray, instrumental: np.ndarray, vocal_gain: float, inst_gain: float
) -> tuple[bytes, float]:
    """Como ``mix``, e devolve também o volume do trecho (RMS, 0–1)."""
    out = vocals * vocal_gain + instrumental * inst_gain
    np.clip(out, -1.0, 1.0, out=out)
    rms = float(np.sqrt(np.mean(np.square(out)))) if out.size else 0.0
    return (out * 32767).astype("<i2").tobytes(), rms


class _MixDevice(QIODevice):
    """Fonte de áudio que a placa de som lê sob demanda (modo pull)."""

    def __init__(self, player: StemPlayer) -> None:
        super().__init__()
        self._player = player

    def readData(self, maxlen: int) -> bytes:
        return self._player._read(maxlen)

    def writeData(self, data) -> int:
        return 0

    def bytesAvailable(self) -> int:
        return self._player._remaining_bytes() + super().bytesAvailable()

    def isSequential(self) -> bool:
        return True


class StemPlayer(QObject):
    loaded = Signal(float)            # duração em segundos
    load_failed = Signal(str)
    position_changed = Signal(float)  # segundos (≈30 vezes por segundo)
    state_changed = Signal(object)    # PlayerState
    finished = Signal()
    # Uso interno: entrega o áudio lido pela thread de carga à thread principal
    _data_ready = Signal(int, object, object, int)
    _data_failed = Signal(int, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._vocals: np.ndarray | None = None
        self._instrumental: np.ndarray | None = None
        self._rate = 44100
        self._frames = 0
        self._cursor = 0       # próximo quadro a ser entregue à placa de som
        self._start_frame = 0  # quadro em que a placa de som começou a tocar
        self._level = 0.0  # volume do último trecho enviado à placa de som
        self.vocal_volume = 1.0
        self.instrumental_volume = 1.0
        self._state = PlayerState.STOPPED
        self._generation = 0  # identifica o carregamento mais recente
        self._sink: QAudioSink | None = None
        self._device = _MixDevice(self)
        self._device.open(QIODevice.OpenModeFlag.ReadOnly)

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self.loaded.connect(self._setup_sink)
        self._data_ready.connect(self._apply_data)
        self._data_failed.connect(self._apply_failure)

    # ------------------------------------------------------------- carga
    def load(self, vocals: Path, instrumental: Path) -> None:
        """Carrega os dois arquivos em segundo plano; emite ``loaded``.

        A thread só lê os arquivos. Os dados são entregues à thread principal
        por sinal, junto com o número do carregamento: resultados de um
        carregamento antigo são ignorados, e se o player já tiver sido fechado
        a entrega é descartada sem erro.
        """
        self.stop()
        self._generation += 1
        generation = self._generation
        if not has_audio_output():
            self.load_failed.emit("nenhuma saída de áudio encontrada")
            return

        def work() -> None:
            try:
                voc, rate_v = load_stem(vocals)
                inst, rate_i = load_stem(instrumental)
                if rate_v != rate_i:
                    raise ValueError("vocais e instrumental com taxas de amostragem diferentes")
                frames = min(len(voc), len(inst))
                result = (self._data_ready, (generation, voc[:frames], inst[:frames], rate_v))
            except Exception as exc:
                result = (self._data_failed, (generation, str(exc) or exc.__class__.__name__))
            signal, args = result
            if not shiboken6.isValid(self):
                return  # player fechado durante a carga
            try:
                signal.emit(*args)
            except RuntimeError:
                pass  # fechado entre a verificação e o envio

        threading.Thread(target=work, name="carregar-audio", daemon=True).start()

    def _apply_data(self, generation: int, vocals, instrumental, rate: int) -> None:
        if generation != self._generation:
            return  # outra música foi aberta nesse meio-tempo
        self._vocals, self._instrumental = vocals, instrumental
        self._rate, self._frames, self._cursor = rate, len(vocals), 0
        self.loaded.emit(self.duration)

    def _apply_failure(self, generation: int, message: str) -> None:
        if generation == self._generation:
            self.load_failed.emit(message)

    def _setup_sink(self, _duration: float) -> None:
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        fmt = QAudioFormat()
        fmt.setSampleRate(self._rate)
        fmt.setChannelCount(CHANNELS)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), fmt, self)
        self._sink.setBufferSize(int(self._rate * BUFFER_SECONDS) * BYTES_PER_FRAME)
        self._sink.stateChanged.connect(self._on_sink_state)

    # ---------------------------------------------------------- consulta
    @property
    def duration(self) -> float:
        return self._frames / self._rate if self._rate else 0.0

    @property
    def state(self) -> PlayerState:
        return self._state

    def position(self) -> float:
        """Posição do que está saindo na caixa de som, em segundos.

        Usa o tempo que a placa de som já tocou desde o último início
        (processedUSecs), que desconta o buffer e a latência do sistema.
        """
        if self._sink is None or self._state is PlayerState.STOPPED:
            return self._cursor / self._rate
        played = self._start_frame + int(self._sink.processedUSecs() * self._rate / 1_000_000)
        return min(played, self._cursor) / self._rate

    @property
    def level(self) -> float:
        """Intensidade do som tocando agora (0–1); zero se não estiver tocando."""
        if self._state is not PlayerState.PLAYING:
            return 0.0
        return min(1.0, self._level * 3.5)  # RMS de música costuma ficar entre 0,05 e 0,3

    # ---------------------------------------------------------- controle
    def play(self) -> None:
        if self._sink is None or self._frames == 0:
            return
        if self._cursor >= self._frames:
            self._cursor = 0
        if self._state is PlayerState.PAUSED:
            self._sink.resume()
        else:
            self._start_frame = self._cursor
            self._sink.start(self._device)
        self._set_state(PlayerState.PLAYING)
        self._timer.start()

    def pause(self) -> None:
        if self._state is PlayerState.PLAYING and self._sink is not None:
            self._sink.suspend()
            self._set_state(PlayerState.PAUSED)
            self._timer.stop()
            self.position_changed.emit(self.position())

    def toggle(self) -> None:
        self.pause() if self._state is PlayerState.PLAYING else self.play()

    def stop(self) -> None:
        if self._sink is not None:
            self._sink.stop()
        self._timer.stop()
        self._cursor = 0
        self._set_state(PlayerState.STOPPED)

    def seek(self, seconds: float) -> None:
        was_playing = self._state is PlayerState.PLAYING
        target = int(min(max(seconds, 0.0), self.duration) * self._rate)
        if self._sink is not None and self._state is not PlayerState.STOPPED:
            self._sink.stop()  # descarta o que já estava no buffer
            self._set_state(PlayerState.STOPPED)
            self._timer.stop()
        self._cursor = target
        if was_playing:
            self.play()
        else:
            self.position_changed.emit(self._cursor / self._rate)

    def set_vocal_volume(self, value: float) -> None:
        self.vocal_volume = max(0.0, value)

    def set_instrumental_volume(self, value: float) -> None:
        self.instrumental_volume = max(0.0, value)

    # ----------------------------------------------------------- interno
    def _remaining_bytes(self) -> int:
        return max(0, self._frames - self._cursor) * BYTES_PER_FRAME

    def _read(self, maxlen: int) -> bytes:
        if self._vocals is None:
            return b""
        frames = min(maxlen // BYTES_PER_FRAME, self._frames - self._cursor)
        if frames <= 0:
            return b""
        start, end = self._cursor, self._cursor + frames
        self._cursor = end
        data, rms = mix_with_level(
            self._vocals[start:end],
            self._instrumental[start:end],
            self.vocal_volume,
            self.instrumental_volume,
        )
        self._level = rms
        return data

    def _tick(self) -> None:
        self.position_changed.emit(self.position())

    def _on_sink_state(self, state) -> None:
        # Idle com o áudio todo entregue = fim da música
        if state == QAudio.State.IdleState and self._cursor >= self._frames:
            self._sink.stop()
            self._timer.stop()
            self._set_state(PlayerState.STOPPED)
            self.position_changed.emit(self.duration)
            self._cursor = 0
            self.finished.emit()

    def _set_state(self, state: PlayerState) -> None:
        if state is not self._state:
            self._state = state
            self.state_changed.emit(state)
