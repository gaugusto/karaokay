"""Coleta de lixo do Python só na thread principal.

O coletor automático do Python pode rodar em qualquer thread, inclusive nas
de segundo plano (download, separação, carga do áudio). Se ele apagar ali um
objeto do Qt criado na thread principal (uma janela fechada, por exemplo), o
Qt derruba o processo com "Segmentation fault". Por isso a coleta automática
é desligada e feita periodicamente pela thread principal, via QTimer.
A contagem de referências continua liberando a memória normalmente; só os
ciclos de objetos esperam a próxima coleta.
"""

from __future__ import annotations

import gc

from PySide6.QtCore import QObject, QTimer

COLLECT_INTERVAL_MS = 3000


def install(parent: QObject, interval_ms: int = COLLECT_INTERVAL_MS) -> QTimer:
    gc.disable()
    timer = QTimer(parent)
    timer.setInterval(interval_ms)
    timer.timeout.connect(gc.collect)
    timer.start()
    return timer
