import logging
import sys

from PySide6 import QtWidgets

import config
from logging_config import setup_logging
from ui import theme
from ui.MainWindow import MainWindow

logger = logging.getLogger(__name__)


def main():
    setup_logging()
    logger.info("Starting goqu")
    app = QtWidgets.QApplication(sys.argv)

    # Apply the saved appearance before building any widget so the first paint
    # is already themed.
    theme.apply(app, theme.resolve_mode(config.get_theme_pref(), app))

    # Track live OS light/dark changes, but only while the user is following the
    # system (checked at fire time so a runtime switch to/from "system" works).
    def _on_os_scheme_changed(*_):
        if config.get_theme_pref() == "system":
            theme.apply(app, theme.resolve_mode("system", app))

    app.styleHints().colorSchemeChanged.connect(_on_os_scheme_changed)

    window = MainWindow()
    window.show()
    exit_code = app.exec()
    logger.info("goqu exited (code=%s)", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
