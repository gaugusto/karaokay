import gc


def test_install_disables_automatic_gc_and_collects_on_timer(qapp):
    from PySide6.QtCore import QObject

    from karaoke import gc_guard

    was_enabled = gc.isenabled()
    parent = QObject()
    timer = gc_guard.install(parent, interval_ms=1000)
    assert not gc.isenabled()
    assert timer.isActive() and timer.interval() == 1000
    timer.stop()
    if was_enabled:
        gc.enable()
