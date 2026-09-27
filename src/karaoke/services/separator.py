"""Separação de vocais com BS-RoFormer (via audio-separator)."""

from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import threading
import warnings
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from karaoke.models.song import INSTRUMENTAL_NAME, VOCALS_NAME, find_stem

# BS-RoFormer treinado por ZFTurbo/viperx (SDR ~12,9 dB nos vocais)
MODEL_FILENAME = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
OUTPUT_FORMAT = "FLAC"  # sem perdas e menor que WAV
SAMPLE_RATE = 44100      # taxa com que o modelo trabalha


def decode_to_wav(source: Path, target: Path) -> None:
    """Decodifica qualquer áudio para WAV estéreo com o ffmpeg.

    O librosa 1.0 (usado pelo audio-separator) só lê os formatos do
    libsndfile; .webm, .m4a e .opus do YouTube precisam ser convertidos.
    Usa float de 32 bits para não perder nada na conversão.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg não encontrado; instale com: sudo pacman -S ffmpeg")
    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source),
            "-vn", "-ac", "2", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_f32le",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1:] or ["erro desconhecido"]
        raise RuntimeError(f"ffmpeg não conseguiu ler o áudio: {detail[0]}")


class _ProgressBar:
    """Substituto mínimo do tqdm que repassa o progresso (0–1) a um callback.

    O audio-separator usa o tqdm para contar os blocos de áudio processados
    pelo modelo e os bytes do download do modelo; trocando o tqdm dos módulos
    dele por esta classe, o app recebe esse progresso sem alterar a biblioteca.
    """

    def __init__(self, callback, iterable=None, total=None, *args, **kwargs) -> None:
        self._callback = callback
        self._iterable = iterable
        if total is None and iterable is not None and hasattr(iterable, "__len__"):
            total = len(iterable)
        self.total = total
        self.n = 0

    def __iter__(self):
        for item in self._iterable:
            yield item
            self.update(1)

    def update(self, n: int = 1) -> None:
        self.n += n
        if self.total:
            self._callback(min(self.n / self.total, 1.0))

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __getattr__(self, name):  # set_description, refresh, etc.: sem efeito
        return lambda *args, **kwargs: None


def _progress_factory(callback):
    return lambda *args, **kwargs: _ProgressBar(callback, *args, **kwargs)


class SeparationService(QObject):
    """Fila que separa vocais e instrumental, uma música por vez.

    O trabalho roda numa thread de fundo (daemon), então fechar o aplicativo
    no meio de uma separação não trava nem derruba nada. O modelo é carregado
    uma única vez, no primeiro pedido. Os arquivos são gerados numa pasta
    temporária e só movidos para o destino quando completos.
    """

    started = Signal(str)          # caminho da música
    progress = Signal(str, int)    # caminho da música, porcentagem (0–100)
    status = Signal(str)           # mensagem para a barra de status
    finished = Signal(str)         # caminho da música
    failed = Signal(str, str)      # caminho da música, mensagem de erro

    def __init__(self, models_dir: Path, work_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._models_dir = models_dir
        self._work_dir = work_dir
        self._separator = None
        self._current: str | None = None
        self._last_percent = -1
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
        # O rotary-embedding-torch 0.6 (versão exigida pelo audio-separator) usa
        # torch.cuda.amp.autocast, que o PyTorch marcou como obsoleto; o aviso é
        # inofensivo e não há versão compatível sem ele, então é silenciado aqui.
        warnings.filterwarnings(
            "ignore",
            message=r"`torch\.cuda\.amp\.autocast\(args\.\.\.\)` is deprecated",
            category=FutureWarning,
        )
        from audio_separator.separator import Separator  # import pesado: só quando precisar

        self._hook_progress()

        self._models_dir.mkdir(parents=True, exist_ok=True)
        separator = Separator(
            log_level=logging.WARNING,
            model_file_dir=str(self._models_dir),
            output_dir=str(self._work_dir),
            output_format=OUTPUT_FORMAT,
        )
        separator.load_model(model_filename=MODEL_FILENAME)
        self._separator = separator

    def _hook_progress(self) -> None:
        """Captura o progresso do audio-separator (ver _ProgressBar)."""
        try:
            import audio_separator.separator.separator as separator_module
            from audio_separator.separator.architectures import mdxc_separator
        except ImportError:
            return
        # BS-RoFormer é um modelo MDXC: blocos de áudio processados
        mdxc_separator.tqdm = _progress_factory(self._on_inference_progress)
        # Download do modelo na primeira vez
        separator_module.tqdm = _progress_factory(
            lambda f: self.status.emit(f"Baixando o modelo de separação: {int(f * 100)}%")
        )

    # Faixas da porcentagem: decodificação 0–2, modelo 2–97, gravação 97–100
    def _report(self, percent: int) -> None:
        if self._current and percent != self._last_percent:
            self._last_percent = percent
            self.progress.emit(self._current, percent)

    def _on_inference_progress(self, fraction: float) -> None:
        self._report(2 + int(fraction * 95))

    def _separate(self, song_path: str, target_dir: Path) -> None:
        self._current = song_path
        self._last_percent = -1
        self.started.emit(song_path)
        self._report(0)
        try:
            self._load()
            self.status.emit(f"Separando vocais: {Path(song_path).stem}")
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir.mkdir(parents=True)
            decoded = self._work_dir / "_entrada.wav"
            decode_to_wav(Path(song_path), decoded)
            self._report(2)
            self._separator.separate(
                str(decoded),
                custom_output_names={"Vocals": VOCALS_NAME, "Instrumental": INSTRUMENTAL_NAME},
            )
            decoded.unlink()
            self._report(97)
            if find_stem(self._work_dir, VOCALS_NAME) is None or find_stem(self._work_dir, INSTRUMENTAL_NAME) is None:
                produced = ", ".join(p.name for p in self._work_dir.iterdir()) or "nada"
                raise RuntimeError(f"o modelo não gerou vocais e instrumental (gerou: {produced})")

            shutil.rmtree(target_dir, ignore_errors=True)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            self._work_dir.rename(target_dir)
        except Exception as exc:
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._current = None
            self.failed.emit(song_path, str(exc) or exc.__class__.__name__)
            return
        self._report(100)
        self._current = None
        self.finished.emit(song_path)
