"""Remoção de arquivos das músicas."""

from __future__ import annotations

import shutil
from pathlib import Path


def delete_paths(paths: list[Path]) -> list[tuple[Path, str]]:
    """Apaga arquivos e pastas; devolve os que falharam, com o motivo."""
    errors: list[tuple[Path, str]] = []
    for path in paths:
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError as exc:
            errors.append((path, exc.strerror or str(exc)))
    return errors
