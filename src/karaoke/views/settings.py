"""Preferências do usuário guardadas entre uma execução e outra."""

from __future__ import annotations

from PySide6.QtCore import QSettings


def settings() -> QSettings:
    """Arquivo de preferências (ex.: ~/.config/karaokay/karaoke.ini no Linux)."""
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "karaokay", "karaoke")


# ------------------------------------------------------------------ MVSEP
MVSEP_TOKEN_KEY = "mvsep/api_token"
MVSEP_TOKEN_ENV = "MVSEP_API_TOKEN"
LAST_METHOD_KEY = "processamento/ultimo_metodo"


def mvsep_token_file():
    """Arquivo opcional com a chave, na raiz do projeto (fora do git)."""
    from karaoke import paths

    return paths.PROJECT_ROOT / ".mvsep-token"


def mvsep_api_token() -> str | None:
    """Chave de API do MVSEP: variável de ambiente MVSEP_API_TOKEN, depois as
    preferências, depois o arquivo .mvsep-token na raiz do projeto."""
    import os

    token = os.environ.get(MVSEP_TOKEN_ENV, "").strip()
    if token:
        return token
    token = str(settings().value(MVSEP_TOKEN_KEY, "") or "").strip()
    if token:
        return token
    try:
        return mvsep_token_file().read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def set_mvsep_api_token(token: str) -> None:
    settings().setValue(MVSEP_TOKEN_KEY, token.strip())


def last_separation_method() -> str | None:
    value = settings().value(LAST_METHOD_KEY, None)
    return str(value) if value else None


def set_last_separation_method(method: str) -> None:
    settings().setValue(LAST_METHOD_KEY, method)
