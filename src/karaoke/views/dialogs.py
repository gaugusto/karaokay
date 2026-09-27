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


def inform(parent: QWidget | None, title: str, text: str) -> None:
    """Aviso simples com botão OK."""
    QMessageBox.information(parent, title, text)


def offer(parent: QWidget | None, title: str, text: str, action: str) -> bool:
    """Aviso com um botão de ação (ex.: "Buscar manualmente…") e "Fechar".
    Devolve True se o usuário escolher a ação."""
    box = QMessageBox(QMessageBox.Icon.Information, title, text, parent=parent)
    action_button = box.addButton(action, QMessageBox.ButtonRole.AcceptRole)
    close_button = box.addButton("Fechar", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(action_button)
    box.setEscapeButton(close_button)
    box.exec()
    return box.clickedButton() is action_button
