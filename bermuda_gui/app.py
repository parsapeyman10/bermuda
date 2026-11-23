"""QApplication bootstrap: theme, offscreen-aware entry point."""
import os, sys

import bermuda_gui.paths  # noqa: F401  (sys.path bootstrap before PyQt import)


def run(argv=None):
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QIcon
    import bermuda_gui.theme as theme
    from bermuda_gui.main_window import MainWindow

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName('black-bermuda-gui')
    app.setOrganizationName('bermuda-detector')
    app.setStyle('Fusion')
    app.setStyleSheet(theme.build_qss())
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'icon.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()
    return app.exec()
