"""Ponto de entrada: python -m karaoke"""

import sys

from PySide6.QtWidgets import QApplication

from karaoke import gc_guard
from karaoke.controllers import AppController
from karaoke.views import MainWindow
from karaoke.views.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Karaokê")
    apply_theme(app)
    gc_guard.install(app)  # evita que threads de fundo apaguem objetos do Qt
    window = MainWindow()
    controller = AppController(window)
    controller.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
