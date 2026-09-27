"""Janela principal do aplicativo."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Karaokê")
        self.resize(1024, 640)

        label = QLabel("🎤 Karaokê")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 48px;")
        self.setCentralWidget(label)
