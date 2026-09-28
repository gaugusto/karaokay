"""Preferências do usuário guardadas entre uma execução e outra."""

from __future__ import annotations

from PySide6.QtCore import QSettings


def settings() -> QSettings:
    """Arquivo de preferências (ex.: ~/.config/karaokay/karaoke.ini no Linux)."""
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "karaokay", "karaoke")
