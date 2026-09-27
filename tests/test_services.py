import sys
import types

import pytest

import karaoke.services.separator as separator_module
from karaoke.services import SeparationService, is_youtube_url


@pytest.mark.parametrize(
    "url, ok",
    [
        ("https://www.youtube.com/watch?v=abc", True),
        ("https://youtu.be/abc", True),
        ("https://music.youtube.com/watch?v=abc", True),
        ("http://m.youtube.com/watch?v=abc", True),
        ("https://exemplo.com/watch?v=abc", False),
        ("youtube.com/watch?v=abc", False),
        ("texto qualquer", False),
    ],
)
def test_is_youtube_url(url, ok):
    assert is_youtube_url(url) is ok


class FakeSeparator:
    fail = False

    def __init__(self, **kw):
        self.kw = kw

    def load_model(self, model_filename):
        pass

    def separate(self, path, custom_output_names=None):
        if FakeSeparator.fail:
            raise RuntimeError("erro simulado")
        from pathlib import Path

        out = Path(self.kw["output_dir"])
        for name in custom_output_names.values():
            (out / f"{name}.flac").write_bytes(b"x")


@pytest.fixture
def service(qapp, tmp_path, monkeypatch):
    pkg = types.ModuleType("audio_separator")
    mod = types.ModuleType("audio_separator.separator")
    mod.Separator = FakeSeparator
    monkeypatch.setitem(sys.modules, "audio_separator", pkg)
    monkeypatch.setitem(sys.modules, "audio_separator.separator", mod)
    monkeypatch.setattr(separator_module, "decode_to_wav", lambda src, dst: dst.write_bytes(b"wav"))
    return SeparationService(tmp_path / "modelos", tmp_path / "trabalho")


def test_separation_publishes_complete_folder(service, tmp_path):
    done = []
    service.finished.connect(done.append)
    target = tmp_path / "separadas" / "musica"
    FakeSeparator.fail = False
    service._separate("musica.m4a", target)
    assert done == ["musica.m4a"]
    assert sorted(p.name for p in target.iterdir()) == ["instrumental.flac", "vocais.flac"]
    assert not (tmp_path / "trabalho").exists()


def test_separation_failure_leaves_nothing_behind(service, tmp_path):
    errors = []
    service.failed.connect(lambda path, msg: errors.append(msg))
    target = tmp_path / "separadas" / "musica"
    FakeSeparator.fail = True
    service._separate("musica.m4a", target)
    assert errors == ["erro simulado"]
    assert not target.exists()
    assert not (tmp_path / "trabalho").exists()


def test_queue_is_fifo_and_never_concurrent(service, tmp_path, qapp):
    import threading
    import time

    from PySide6.QtCore import QEventLoop, QTimer

    active, peak, order = [0], [0], []
    lock = threading.Lock()
    original = FakeSeparator.separate

    def slow_separate(self, path, custom_output_names=None):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        original(self, path, custom_output_names)
        with lock:
            active[0] -= 1

    FakeSeparator.fail = False
    FakeSeparator.separate = slow_separate
    try:
        loop = QEventLoop()
        service.started.connect(order.append)
        service.finished.connect(lambda p: loop.quit() if p == "m4" else None)
        for name in ["m1", "m2", "m3", "m4"]:
            service.enqueue(name, tmp_path / "separadas" / name)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
    finally:
        FakeSeparator.separate = original

    assert order == ["m1", "m2", "m3", "m4"]
    assert peak[0] == 1
