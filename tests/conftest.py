import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def dirs(tmp_path):
    music = tmp_path / "músicas"
    separated = music / "separadas"
    music.mkdir()
    return music, separated


def add_song(music: Path, name: str) -> Path:
    path = music / name
    path.write_bytes(b"x")
    return path


def add_stems(separated: Path, stem: str) -> None:
    folder = separated / stem
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "vocais.flac").write_bytes(b"x")
    (folder / "instrumental.flac").write_bytes(b"x")
