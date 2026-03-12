"""Error log file handler and warning count for progress bar."""

import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional, Union

_WINDOW_SECONDS = 30
_lock = threading.Lock()
_warning_times: deque = deque(maxlen=10000)


def _trim() -> None:
    """Keep only timestamps from the last _WINDOW_SECONDS."""
    now = time.time()
    while _warning_times and _warning_times[0] < now - _WINDOW_SECONDS:
        _warning_times.popleft()


def get_warning_count_last_30s() -> int:
    """Return number of WARNING+ log records in the last 30 seconds."""
    with _lock:
        _trim()
        return len(_warning_times)


def _record_warning() -> None:
    with _lock:
        _warning_times.append(time.time())


class ErrorLogHandler(logging.Handler):
    """Writes WARNING+ to a file and records timestamps for last-30s count."""

    def __init__(self, filepath: Union[str, Path]) -> None:
        super().__init__(level=logging.WARNING)
        self._path = Path(filepath)
        self.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        _record_warning()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)


def setup_error_log(
    filepath: Union[str, Path],
    logger_names: Optional[list[str]] = None,
) -> None:
    """Attach ErrorLogHandler to given loggers (default: uniswap_fetcher.* and root)."""
    handler = ErrorLogHandler(filepath)
    if logger_names:
        for name in logger_names:
            logging.getLogger(name).addHandler(handler)
    else:
        logging.getLogger("uniswap_fetcher").addHandler(handler)
        logging.getLogger("urllib3").addHandler(handler)
