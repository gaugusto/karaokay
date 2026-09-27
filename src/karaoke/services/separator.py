"""Separação de vocais com BS-RoFormer (via audio-separator)."""

from __future__ import annotations

import logging
import queue
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from karaoke.models.song import INSTRUMENTAL_NAME, VOCALS_NAME, find_stem

# BS-RoFormer treinado por ZFTurbo/viperx (SDR ~12,9 dB nos vocais)
MODEL_FILENAME = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
OUTPUT_FORMAT = "FLAC"  # sem perdas e menor que WAV


class SeparationService(QObject):
    """Fila que separa vocais e instrumental, uma música por vez.

    O trabalho roda numa thread de fundo (daemon), então fechar o aplicativo
    no meio de uma separação não trava nem derruba nada. O modelo é carregado
    uma única vez, no primeiro pedido. Os arquivos são gerados numa pasta
    temporária e só movidos para o destino quando completos.
    """

    started = Signal(str)          # caminho da música
    status = Signal(str)           # mensagem para a barra de status
    finished = Signal(str)         # caminho da música
    failed = Signal(str, str)      # caminho da música, mensagem de erro

    def __init__(self, models_dir: Path, work_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._models_dir = models_dir
        self._work_dir = work_dir
        self._separator = None
        self._queue: queue.Queue[tuple[str, Path]] = queue.Queue()
        threading.Thread(target=self._loop, name="separacao", daemon=True).start()

    def enqueue(self, song_path: str | Path, target_dir: Path) -> None:
        """Separa ``song_path`` e grava vocais/instrumental em ``target_dir``."""
        self._queue.put((str(song_path), target_dir))

    # --------------------------------------------------------------- interno
    def _loop(self) -> None:
        while True:
            self._separate(*self._queue.get())

    def _load(self) -> None:
        if self._separator is not None:
            return
        self.status.emit("Carregando o modelo de separação (na primeira vez ele é baixado)…")
        from audio_separator.separator import Separator  # import pesado: só quando precisar

        self._models_dir.mkdir(parents=True, exist_ok=True)
        separator = Separator(
            log_level=logging.WARNING,
            model_file_dir=str(self._models_dir),
            output_dir=str(self._work_dir),
            output_format=OUTPUT_FORMAT,
        )
        separator.load_model(model_filename=MODEL_FILENAME)
        self._separator = separator

    def _separate(self, song_path: str, target_dir: Path) -> None:
        self.started.emit(song_path)
        try:
            self._load()
            self.status.emit(f"Separando vocais: {Path(song_path).stem}")
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir.mkdir(parents=True)
            self._separator.separate(
                song_path,
                custom_output_names={"Vocals": VOCALS_NAME, "Instrumental": INSTRUMENTAL_NAME},
            )
            if find_stem(self._work_dir, VOCALS_NAME) is None or find_stem(self._work_dir, INSTRUMENTAL_NAME) is None:
                produced = ", ".join(p.name for p in self._work_dir.iterdir()) or "nada"
                raise RuntimeError(f"o modelo não gerou vocais e instrumental (gerou: {produced})")

            shutil.rmtree(target_dir, ignore_errors=True)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            self._work_dir.rename(target_dir)
        except Exception as exc:
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self.failed.emit(song_path, str(exc) or exc.__class__.__name__)
            return
        self.finished.emit(song_path)
