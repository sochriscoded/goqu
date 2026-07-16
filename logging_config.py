"""Application logging setup — stdlib `logging` with a rotating file handler.

Call `setup_logging()` once at startup (see main.py). Everywhere else, use the
standard idiom and let messages propagate to the root logger configured here:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("…")

Log file:   ~/.config/goqu/logs/goqu.log  (rotated, 1 MB × 5 backups)
Level:      INFO by default; override with the GOQU_LOG_LEVEL env var
            (e.g. GOQU_LOG_LEVEL=DEBUG) or the `level` argument.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "goqu" / "logs"
LOG_FILE = LOG_DIR / "goqu.log"

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_DEFAULT_LEVEL = "INFO"

# Third-party loggers that are noisy at DEBUG — keep our log readable.
_NOISY = ("urllib3", "yfinance", "peewee", "matplotlib", "PIL")

_configured = False


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger. Idempotent — safe to call more than once."""
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level_name = (level or os.environ.get("GOQU_LOG_LEVEL") or _DEFAULT_LEVEL).upper()
    log_level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()  # stderr, for dev
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Send otherwise-unhandled exceptions to the log before the app dies.
    sys.excepthook = _log_uncaught

    _configured = True
    logging.getLogger(__name__).info(
        "Logging initialized (level=%s) -> %s", level_name, LOG_FILE
    )


def _log_uncaught(exc_type, exc_value, exc_tb):
    # Let Ctrl-C behave normally; log everything else with a traceback.
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.getLogger("goqu").critical(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb)
    )
