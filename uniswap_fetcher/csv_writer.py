"""CSV writer that organises output by pair and event type (thread-safe)."""

import csv
import logging
import threading
from pathlib import Path
from typing import List, TextIO, Union

from .models import BurnEvent, MintEvent, SwapEvent, SyncEvent

logger = logging.getLogger(__name__)

_EVENT_FILE_MAP: dict[type, tuple[str, list[str]]] = {
    SwapEvent: ("swaps.csv", SwapEvent.CSV_HEADERS),
    SyncEvent: ("syncs.csv", SyncEvent.CSV_HEADERS),
    MintEvent: ("mints.csv", MintEvent.CSV_HEADERS),
    BurnEvent: ("burns.csv", BurnEvent.CSV_HEADERS),
}


class CSVWriter:
    """Writes decoded events to per-pair, per-event-type CSV files.

    Directory layout::

        <output_dir>/
          <pair_name>/
            swaps.csv
            syncs.csv
            mints.csv
            burns.csv
    """

    def __init__(self, output_dir: Union[str, Path]) -> None:
        self._output_dir = Path(output_dir)
        self._handles: dict[str, tuple[TextIO, csv.writer]] = {}
        self._lock = threading.RLock()

    def _get_writer(
        self,
        pair_name: str,
        event_type: type,
    ) -> csv.writer:
        """Return (and lazily create) a csv.writer for the given pair + event type."""
        filename, headers = _EVENT_FILE_MAP[event_type]
        key = f"{pair_name}/{filename}"
        with self._lock:
            if key not in self._handles:
                pair_dir = self._output_dir / pair_name
                pair_dir.mkdir(parents=True, exist_ok=True)
                filepath = pair_dir / filename
                file_exists = filepath.exists() and filepath.stat().st_size > 0
                fh = open(filepath, "a", newline="", encoding="utf-8")  # noqa: SIM115
                writer = csv.writer(fh)
                if not file_exists:
                    writer.writerow(headers)
                    fh.flush()
                self._handles[key] = (fh, writer)
                logger.debug("Opened CSV file: %s", filepath)
            return self._handles[key][1]

    def write_events(
        self,
        pair_name: str,
        events: List[Union[SwapEvent, SyncEvent, MintEvent, BurnEvent]],
    ) -> int:
        """Write a batch of decoded events to the appropriate CSV files.

        Args:
            pair_name: Human-readable pair name used as directory name.
            events: List of decoded event dataclass instances.

        Returns:
            Number of events written.
        """
        with self._lock:
            count = 0
            for event in events:
                event_type = type(event)
                if event_type not in _EVENT_FILE_MAP:
                    logger.warning("Unknown event type: %s", event_type)
                    continue
                writer = self._get_writer(pair_name, event_type)
                writer.writerow(event.to_row())
                count += 1
            self.flush()
        return count

    def flush(self) -> None:
        """Flush all open file handles."""
        with self._lock:
            for fh, _ in self._handles.values():
                fh.flush()

    def close(self) -> None:
        """Close all open file handles."""
        with self._lock:
            for fh, _ in self._handles.values():
                try:
                    fh.close()
                except Exception:
                    logger.exception("Error closing CSV file handle")
            self._handles.clear()
