"""Fundo animado: controle, reação à música e legibilidade da letra."""

import numpy as np
import pytest
from PySide6.QtGui import QColor

from karaoke.views.background import AnimatedBackground
from karaoke.views.theme import Colors


def _luminance(c: QColor) -> float:
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(c.red()) + 0.7152 * channel(c.green()) + 0.0722 * channel(c.blue())


def _contrast(a: QColor, b: QColor) -> float:
    la, lb = sorted([_luminance(a), _luminance(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _brightest(bg, bands):
    """Pixel mais claro em cada faixa (fração da altura), ao longo da animação."""
    worst = {name: QColor(Colors.BACKGROUND) for name in bands}
    for _ in range(24):
        bg.advance(5.0)  # 2 minutos de animação
        img = bg.grab().toImage()
        for y in range(0, img.height(), 10):
            for name, (top, bottom) in bands.items():
                if top <= y / img.height() <= bottom:
                    for x in range(0, img.width(), 10):
                        c = img.pixelColor(x, y)
                        if _luminance(c) > _luminance(worst[name]):
                            worst[name] = c
    return worst


def test_lyrics_stay_readable_over_the_effect(qapp):
    """Mesmo com o brilho no máximo, no pior momento da animação:
    verso atual (sempre no meio) >= 4,5:1 e demais versos >= 3:1 (texto grande)."""
    bg = AnimatedBackground()
    bg.resize(860, 520)
    bg.show()
    bg.set_level(1.0)
    for _ in range(60):
        bg.advance(0)
    worst = _brightest(bg, {"meio": (0.4, 0.6), "tudo": (0.0, 1.0)})
    assert _contrast(QColor(Colors.ACCENT_HOVER), worst["meio"]) >= 4.5
    assert _contrast(QColor(Colors.LYRICS_DIM), worst["tudo"]) >= 3.0
    assert _contrast(QColor(Colors.TEXT), worst["tudo"]) >= 7.0


def test_effect_can_be_turned_off_and_only_animates_when_visible(qapp):
    bg = AnimatedBackground()
    assert not bg.animating  # escondido: parado
    bg.show()
    assert bg.animating
    bg.set_effect_enabled(False)
    assert not bg.animating
    img = bg.grab().toImage()
    assert img.pixelColor(img.width() // 3, img.height() // 3) == QColor(Colors.BACKGROUND)
    bg.set_effect_enabled(True)
    bg.hide()
    assert not bg.animating


def test_level_is_smoothed(qapp):
    bg = AnimatedBackground()
    bg.set_level(1.0)
    bg.advance(0.033)
    assert 0 < bg._level < 0.5  # sobe aos poucos, sem piscar
    for _ in range(80):
        bg.advance(0.033)
    assert bg._level == pytest.approx(1.0, abs=0.01)
    bg.set_level(5)  # limitado a 1
    assert bg._target == 1.0


def test_player_level_follows_music(qapp):
    from karaoke.services.stem_player import PlayerState, StemPlayer

    player = StemPlayer()
    frames = 1000
    player._vocals = np.full((frames, 2), 0.05, dtype="float32")
    player._instrumental = np.full((frames, 2), 0.05, dtype="float32")
    player._frames, player._rate = frames, 1000
    player._read(400 * 4)
    assert player.level == 0.0  # parado: fundo calmo
    player._state = PlayerState.PLAYING
    assert player.level == pytest.approx(0.10 * 3.5, rel=0.01)  # voz + instrumental = 0,10
    player.set_vocal_volume(0)
    player._read(400 * 4)
    assert player.level == pytest.approx(0.05 * 3.5, rel=0.01)


def test_player_window_toggle_is_remembered(qapp):
    from karaoke.views import PlayerWindow
    from karaoke.views.player_window import _settings

    _settings().remove("player/background_effect")
    view = PlayerWindow()
    assert view.effect_button.isChecked() and view.background.effect_enabled
    view.effect_button.click()
    assert not view.background.effect_enabled
    assert not PlayerWindow().effect_button.isChecked()  # lembrado
    _settings().remove("player/background_effect")
