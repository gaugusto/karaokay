"""Diálogos simples usados pelas janelas."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def confirm(parent: QWidget | None, title: str, text: str) -> bool:
    """Pergunta Sim/Não; "Não" é o padrão (Enter/Esc não fecham sem querer)."""
    answer = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes
