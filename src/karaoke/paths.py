"""Caminhos usados pelo aplicativo."""

from pathlib import Path

# Raiz do projeto: .../src/karaoke/paths.py -> sobe três níveis
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Pasta onde as músicas baixadas ficam guardadas (ignorada pelo git)
MUSIC_DIR = PROJECT_ROOT / "músicas"

# Vocais e instrumentais separados: músicas/separadas/<nome da música>/
SEPARATED_DIR = MUSIC_DIR / "separadas"

# Letras baixadas do LRCLIB: letras/<nome do áudio>.lrc (sincronizada) ou .txt
LYRICS_DIR = PROJECT_ROOT / "letras"

# Metadados do YouTube (título, artista, canal, duração) usados na busca da letra
METADATA_DIR = MUSIC_DIR / ".metadados"

# Modelos de separação baixados automaticamente (ignorada pelo git)
MODELS_DIR = PROJECT_ROOT / "modelos"

# Extensões de áudio reconhecidas na biblioteca
AUDIO_EXTENSIONS = {
    ".m4a", ".webm", ".opus", ".ogg", ".mp3", ".aac", ".flac", ".wav",
}
