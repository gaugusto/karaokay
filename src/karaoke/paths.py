"""Caminhos usados pelo aplicativo."""

from pathlib import Path

# Raiz do projeto: .../src/karaoke/paths.py -> sobe três níveis
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Pasta onde as músicas baixadas ficam guardadas (ignorada pelo git)
MUSIC_DIR = PROJECT_ROOT / "músicas"

# Extensões de áudio reconhecidas na biblioteca
AUDIO_EXTENSIONS = {
    ".m4a", ".webm", ".opus", ".ogg", ".mp3", ".aac", ".flac", ".wav",
}
