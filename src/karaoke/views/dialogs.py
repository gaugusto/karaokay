"""Diálogos simples usados pelas janelas."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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


_METHOD_DETAILS = {
    SeparationMethod.LOCAL: "Roda neste computador, na placa de vídeo. Não depende da internet.",
    SeparationMethod.MVSEP: "Envia o áudio ao mvsep.com e baixa o resultado. Não pesa no "
    "computador, mas depende da internet e da fila do site.",
}


class SeparationMethodDialog(QDialog):
    """Escolha do método de processamento: uma opção grande por método,
    empilhadas (os textos nunca são cortados), e Cancelar embaixo."""

    WIDTH = 480

    def __init__(self, parent: QWidget | None, default: SeparationMethod) -> None:
        super().__init__(parent)
        self.setWindowTitle("Método de processamento")
        self.setModal(True)
        self.choice: SeparationMethod | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Como separar os vocais desta música?")
        title.setObjectName("dialogTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        self.buttons: dict[SeparationMethod, QPushButton] = {}
        for method in SeparationMethod:
            button = QPushButton(f"{method.label}\n{_METHOD_DETAILS[method]}")
            button.setObjectName("optionButton")
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, m=method: self._choose(m))
            layout.addWidget(button)
            self.buttons[method] = button

        footer = QHBoxLayout()
        footer.addWidget(QLabel("Enter repete a última escolha.", objectName="hint"))
        footer.addStretch(1)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)
        layout.addSpacing(4)
        layout.addLayout(footer)

        self._wrap_option_texts()
        preferred = self.buttons[default]
        preferred.setDefault(True)  # Enter escolhe o último método usado
        preferred.setFocus()
        self.setFixedWidth(self.WIDTH)
        self.adjustSize()

    def _wrap_option_texts(self) -> None:
        """QPushButton não quebra linhas sozinho: quebra a descrição na
        largura disponível para o texto aparecer inteiro."""
        metrics = self.fontMetrics()
        margins = self.layout().contentsMargins()
        # largura do botão menos o padding e a borda do tema
        available = self.WIDTH - margins.left() - margins.right() - 2 * 18 - 20
        for method, button in self.buttons.items():
            words, lines, line = _METHOD_DETAILS[method].split(), [], ""
            for word in words:
                candidate = f"{line} {word}".strip()
                if line and metrics.horizontalAdvance(candidate) > available:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            button.setText("\n".join([method.label, *lines]))

    def _choose(self, method: SeparationMethod) -> None:
        self.choice = method
        self.accept()


def choose_separation_method(parent: QWidget | None, default: SeparationMethod) -> SeparationMethod | None:
    """Pergunta como processar a música adicionada; None se cancelar.

    O botão padrão (Enter) é o último método escolhido.
    """
    dialog = SeparationMethodDialog(parent, default)
    dialog.exec()
    return dialog.choice


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
