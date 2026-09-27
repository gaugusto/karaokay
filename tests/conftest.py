import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def gc_on_main_thread():
    """Como no app (karaoke.gc_guard): sem coleta automática, que poderia rodar
    numa thread de fundo e apagar janelas do Qt fora da thread principal."""
    import gc

    gc.disable()
    yield
    gc.enable()


@pytest.fixture(autouse=True)
def collect_after_test():
    import gc

    yield
    gc.collect()  # na thread principal


@pytest.fixture(scope="session", autouse=True)
def isolated_settings(tmp_path_factory):
    """Preferências (QSettings) numa pasta temporária, nunca no ~/.config real."""
    from PySide6.QtCore import QSettings

    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path_factory.mktemp("config")))


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


def add_song(music: Path, name: str, mtime: float | None = None) -> Path:
    path = music / name
    path.write_bytes(b"x")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def add_stems(separated: Path, stem: str) -> None:
    folder = separated / stem
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "vocais.flac").write_bytes(b"x")
    (folder / "instrumental.flac").write_bytes(b"x")
