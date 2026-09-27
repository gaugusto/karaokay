"""Separação de vocais com BS-RoFormer (via audio-separator)."""

from __future__ import annotations

import logging
import queue
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from karaoke.paths import MODELS_DIR, SEPARATED_DIR

# BS-RoFormer treinado por ZFTurbo/viperx (SDR ~12,9 dB nos vocais)
MODEL_FILENAME = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
OUTPUT_FORMAT = "FLAC"  # sem perdas e menor que WAV

VOCALS_NAME = "vocais"
INSTRUMENTAL_NAME = "instrumental"


def stems_dir(song: Path) -> Path:
    """Pasta com os arquivos separados de uma música."""
    return SEPARATED_DIR / song.stem


def _find(folder: Path, name: str) -> Path | None:
    matches = sorted(folder.glob(f"{name}.*")) if folder.is_dir() else []
    return matches[0] if matches else None


def vocals_path(song: Path) -> Path | None:
    return _find(stems_dir(song), VOCALS_NAME)


def instrumental_path(song: Path) -> Path | None:
    return _find(stems_dir(song), INSTRUMENTAL_NAME)


def is_separated(song: Path) -> bool:
    return vocals_path(song) is not None and instrumental_path(song) is not None


class SeparationWorker(QObject):
    """Fila que separa vocais e instrumental, uma música por vez.

    O trabalho roda numa thread de fundo (daemon), então fechar o aplicativo
    no meio de uma separação não trava nem derruba nada; a música fica sem
    separação e volta para a fila na próxima abertura. O modelo é carregado
    uma única vez, no primeiro pedido, e reaproveitado nos seguintes.
    Os sinais chegam à interface pela fila de eventos do Qt.
    """

    started = Signal(str)            # caminho da música
    status = Signal(str)             # mensagem para a barra de status
    finished = Signal(str, str)      # caminho da música, pasta dos arquivos separados
    failed = Signal(str, str)        # caminho da música, mensagem de erro

    def __init__(self) -> None:
        super().__init__()
        self._separator = None
        self._work_dir = SEPARATED_DIR / ".em-andamento"
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="separacao", daemon=True)
        self._thread.start()

    def enqueue(self, song_path: str) -> None:
        """Coloca uma música na fila de separação."""
        self._queue.put(song_path)

    def _loop(self) -> None:
        while True:
            self._separate(self._queue.get())

    def _load(self) -> None:
        if self._separator is not None:
            return
        self.status.emit("Carregando o modelo de separação (na primeira vez ele é baixado)…")
        from audio_separator.separator import Separator  # import pesado: só quando precisar

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        separator = Separator(
            log_level=logging.WARNING,
            model_file_dir=str(MODELS_DIR),
            output_dir=str(self._work_dir),
            output_format=OUTPUT_FORMAT,
        )
        separator.load_model(model_filename=MODEL_FILENAME)
        self._separator = separator

    def _separate(self, song_path: str) -> None:
        song = Path(song_path)
        self.started.emit(song_path)
        try:
            self._load()
            self.status.emit(f"Separando vocais: {song.stem}")

            # Trabalha numa pasta temporária e só move no final, para que uma
            # separação interrompida nunca pareça concluída.
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir.mkdir(parents=True)
            self._separator.separate(
                str(song),
                custom_output_names={
                    "Vocals": VOCALS_NAME,
                    "Instrumental": INSTRUMENTAL_NAME,
                },
            )
            if _find(self._work_dir, VOCALS_NAME) is None or _find(self._work_dir, INSTRUMENTAL_NAME) is None:
                produced = ", ".join(p.name for p in self._work_dir.iterdir()) or "nada"
                raise RuntimeError(f"o modelo não gerou vocais e instrumental (gerou: {produced})")

            target = stems_dir(song)
            shutil.rmtree(target, ignore_errors=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._work_dir.rename(target)
        except Exception as exc:
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self.failed.emit(song_path, str(exc) or exc.__class__.__name__)
            return
        self.finished.emit(song_path, str(target))
