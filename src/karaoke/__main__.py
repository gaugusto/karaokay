"""Ponto de entrada: python -m karaoke"""

import sys

from PySide6.QtWidgets import QApplication

from karaoke.controllers import AppController
from karaoke.views import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Karaokê")
    window = MainWindow()
    controller = AppController(window)
    controller.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
