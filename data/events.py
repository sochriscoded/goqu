"""Application-wide data event bus.

A single QObject whose signals announce data changes. The DataService emits on
it; views connect to it to stay responsive. Because Qt signals are thread-safe
and delivered on the receiver's thread, background (worker-thread) fetches can
emit here and the UI updates safely on the main thread.

This is the extension point for "responsive to data changes": anything added
later (new data types, live feeds) emits on the bus, and any view refreshes by
connecting to it — no direct coupling between producers and consumers.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class DataEventBus(QObject):
    daily_updated = Signal(str)          # symbol
    quote_updated = Signal(str, float)   # symbol, price
    dividends_updated = Signal(str)      # symbol
    options_updated = Signal(str)        # symbol
    corporate_actions_updated = Signal(str)  # symbol (holdings may have changed)
    metadata_updated = Signal(str)       # symbol (company/sector profile changed)
    data_error = Signal(str, str)        # context, message


_bus: DataEventBus | None = None


def event_bus() -> DataEventBus:
    """Return the process-wide event bus (created lazily)."""
    global _bus
    if _bus is None:
        _bus = DataEventBus()
    return _bus
