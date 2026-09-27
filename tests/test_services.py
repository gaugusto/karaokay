import sys
import types

import pytest

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
