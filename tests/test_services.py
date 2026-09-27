import sys
import types
from pathlib import Path

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
    song = _audio(tmp_path, "musica.m4a")
    service._separate(song, target)
    assert done == [song]
    assert sorted(p.name for p in target.iterdir()) == ["instrumental.flac", "vocais.flac"]
    assert not (tmp_path / "trabalho").exists()


def test_separation_failure_leaves_nothing_behind(service, tmp_path):
    errors = []
    service.failed.connect(lambda path, msg: errors.append(msg))
    target = tmp_path / "separadas" / "musica"
    FakeSeparator.fail = True
    service._separate(_audio(tmp_path, "musica.m4a"), target)
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
        service.started.connect(lambda p: order.append(Path(p).name))
        service.finished.connect(lambda p: loop.quit() if Path(p).name == "m4" else None)
        for name in ["m1", "m2", "m3", "m4"]:
            service.enqueue(_audio(tmp_path, name), tmp_path / "separadas" / name)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
    finally:
        FakeSeparator.separate = original

    assert order == ["m1", "m2", "m3", "m4"]
    assert peak[0] == 1


def test_progress_bar_replacement_reports_fractions():
    from karaoke.services.separator import _progress_factory

    seen = []
    tqdm = _progress_factory(seen.append)
    assert list(tqdm([10, 20, 30, 40])) == [10, 20, 30, 40]
    assert seen == [0.25, 0.5, 0.75, 1.0]

    seen.clear()
    with tqdm(total=200, unit="iB", unit_scale=True) as bar:  # como no download
        bar.update(50)
        bar.set_description("ignorado")
        bar.update(150)
    assert seen == [0.25, 1.0]


def test_separation_reports_percent(service, tmp_path):
    percents = []
    service.progress.connect(lambda path, p: percents.append(p))
    FakeSeparator.fail = False
    original = FakeSeparator.separate

    def separate_in_chunks(self, path, custom_output_names=None):
        # o audio-separator chama o tqdm do módulo mdxc para cada bloco
        for _ in separator_module_mdxc.tqdm(range(4)):
            pass
        original(self, path, custom_output_names)

    FakeSeparator.separate = separate_in_chunks
    try:
        service._hook_progress = lambda: None
        separator_module_mdxc.tqdm = __import__(
            "karaoke.services.separator", fromlist=["_progress_factory"]
        )._progress_factory(service._on_inference_progress)
        service._separate(_audio(tmp_path, "musica.m4a"), tmp_path / "separadas" / "musica")
    finally:
        FakeSeparator.separate = original
    assert percents == [0, 2, 25, 49, 73, 97, 100]


class _Mdxc:
    tqdm = None


separator_module_mdxc = _Mdxc


def _audio(folder, name):
    path = folder / name
    path.write_bytes(b"x")
    return str(path)
