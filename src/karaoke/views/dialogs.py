"""Diálogos simples usados pelas janelas."""

from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from karaoke.models.song import SeparationMethod


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


def choose_separation_method(parent: QWidget | None, default: SeparationMethod) -> SeparationMethod | None:
    """Pergunta como processar a música adicionada; None se cancelar.

    O botão padrão (Enter) é o último método escolhido.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Método de processamento")
    box.setText("Como separar os vocais desta música?")
    box.setInformativeText(
        "• Local (BS-RoFormer): roda neste computador; usa a placa de vídeo.\n"
        "• MVSEP (nuvem): envia o áudio ao mvsep.com e baixa o resultado; "
        "não pesa no computador, mas depende da internet e da fila do site."
    )
    buttons = {
        method: box.addButton(method.label, QMessageBox.ButtonRole.AcceptRole)
        for method in SeparationMethod
    }
    cancel = box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(buttons[default])
    box.setEscapeButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    for method, button in buttons.items():
        if clicked is button:
            return method
    return None


def ask_mvsep_token(parent: QWidget | None) -> str | None:
    """Pede a chave de API do MVSEP (mvsep.com → Perfil → API); None se cancelar."""
    token, ok = QInputDialog.getText(
        parent,
        "Chave do MVSEP",
        "Cole a sua chave de API do MVSEP\n(em mvsep.com, na página do seu perfil):",
        QLineEdit.EchoMode.Password,
    )
    token = token.strip()
    return token if ok and token else None
