"""Ponto de entrada: python -m karaoke"""

import sys

from PySide6.QtWidgets import QApplication

from karaoke.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Karaokê")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
