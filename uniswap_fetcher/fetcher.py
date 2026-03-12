"""Core fetching logic with adaptive block stepping and checkpoint resume."""

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Union

OptionalPairStartCallback = Optional[Callable[[str, str], None]]

from tqdm import tqdm

from .csv_writer import CSVWriter
from .etherscan_client import EtherscanClient
from .event_decoder import DecodedEvent, decode_log
from .models import TOPIC_TO_NAME

logger = logging.getLogger(__name__)

_DEFAULT_BLOCK_STEP = 25000
_MIN_BLOCK_STEP = 500
_MAX_BLOCK_STEP = 80000
_ETHERSCAN_MAX_RECORDS = 1000
_SPARSE_THRESHOLD = 500   # below this: step *= 3.5
_MEDIUM_THRESHOLD = 900   # below this: step *= 3; else step *= 2.5
_SHRINK_FACTOR = 0.9     # on hit_limit: step *= this (minimal shrink)


@dataclass
class PairConfig:
    """Configuration for a single trading pair to fetch."""

    address: str
    name: str


# ---------------------------------------------------------------------------
# Checkpoint persistence
# ---------------------------------------------------------------------------

class CheckpointManager:
    """Manages fetch progress checkpoints in a JSON file (thread-safe)."""

    def __init__(self, filepath: Union[str, Path]) -> None:
        self._filepath = Path(filepath)
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if self._filepath.exists():
            with open(self._filepath, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info(
                "Loaded checkpoint with %d pair(s).", len(self._data),
            )

    def _save_unsafe(self) -> None:
        """Write checkpoint to disk (caller must hold self._lock)."""
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def save(self) -> None:
        """Persist current checkpoint state to disk."""
        with self._lock:
            self._save_unsafe()

    @property
    def pair_count(self) -> int:
        """Return the number of pairs in the checkpoint."""
        with self._lock:
            return len(self._data)

    def get_last_block(self, pair_address: str) -> Optional[int]:
        """Return the last successfully fetched block for a pair, or None."""
        with self._lock:
            entry = self._data.get(pair_address.lower())
            if entry:
                return entry.get("last_block")
        return None

    def update(
        self,
        pair_address: str,
        pair_name: str,
        last_block: int,
        event_counts: dict[str, int],
    ) -> None:
        """Update checkpoint for a pair."""
        with self._lock:
            key = pair_address.lower()
            existing = self._data.get(key, {})
            merged_counts = dict(existing.get("event_counts", {}))
            for evt_name, cnt in event_counts.items():
                merged_counts[evt_name] = merged_counts.get(evt_name, 0) + cnt

            self._data[key] = {
                "pair_name": pair_name,
                "last_block": last_block,
                "event_counts": merged_counts,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            self._save_unsafe()


# ---------------------------------------------------------------------------
# Main fetcher
# ---------------------------------------------------------------------------

class LogFetcher:
    """Fetches and processes UniswapV2 event logs for configured pairs."""

    def __init__(
        self,
        client: EtherscanClient,
        csv_writer: CSVWriter,
        checkpoint: CheckpointManager,
        block_step: int = _DEFAULT_BLOCK_STEP,
        get_warning_count: Optional[Callable[[], int]] = None,
        on_pair_start: OptionalPairStartCallback = None,
        static_step: bool = False,
    ) -> None:
        self._client = client
        self._writer = csv_writer
        self._checkpoint = checkpoint
        self._block_step = block_step
        self._get_warning_count = get_warning_count
        self._on_pair_start = on_pair_start
        self._static_step = static_step

    def fetch_pair(
        self,
        pair: PairConfig,
        from_block: int,
        to_block: int,
    ) -> None:
        """Fetch all events for a single pair across the given block range.

        Automatically resumes from the last checkpoint if available.
        """
        if self._on_pair_start:
            self._on_pair_start(pair.name, pair.address)
        resume_block = self._checkpoint.get_last_block(pair.address)
        if resume_block is not None and resume_block >= from_block:
            actual_start = resume_block + 1
            logger.info(
                "Resuming %s from block %d (checkpoint).",
                pair.name, actual_start,
            )
        else:
            actual_start = from_block

        if actual_start > to_block:
            logger.info(
                "%s: already up to date (last_block=%d >= to_block=%d).",
                pair.name, actual_start - 1, to_block,
            )
            return

        total_blocks = to_block - actual_start + 1
        step = self._block_step

        with tqdm(
            total=total_blocks,
            desc=f"Fetching {pair.name}",
            unit="blk",
            leave=True,
        ) as pbar:
            current = actual_start
            while current <= to_block:
                chunk_end = min(current + step - 1, to_block)
                events, hit_limit = self._fetch_block_range(
                    pair.address, current, chunk_end,
                )

                # At minimum step (or static_step) we advance even if we hit 1000 records
                at_min_step = step <= _MIN_BLOCK_STEP
                if hit_limit and not at_min_step and not self._static_step:
                    step = max(_MIN_BLOCK_STEP, int(step * _SHRINK_FACTOR))
                    logger.debug(
                        "Hit 1000-record limit, shrinking step to %d.", step,
                    )
                    continue

                if events:
                    event_counts = self._count_events(events)
                    written = self._writer.write_events(pair.name, events)
                    self._checkpoint.update(
                        pair.address, pair.name, chunk_end, event_counts,
                    )
                    postfix = {"events": written, "step": step}
                else:
                    self._checkpoint.update(
                        pair.address, pair.name, chunk_end, {},
                    )
                    postfix = {"step": step}
                if self._get_warning_count:
                    postfix["warn_30s"] = self._get_warning_count()
                pbar.set_postfix(postfix, refresh=False)

                advanced = chunk_end - current + 1
                pbar.update(advanced)
                current = chunk_end + 1

                # Adaptive step (skip when static_step)
                if not self._static_step:
                    num_events = len(events) if events else 0
                    if step < _MAX_BLOCK_STEP:
                        if num_events < _SPARSE_THRESHOLD:
                            step = min(_MAX_BLOCK_STEP, int(step * 3.5))
                        elif num_events < _MEDIUM_THRESHOLD or step < _DEFAULT_BLOCK_STEP:
                            step = min(_MAX_BLOCK_STEP, int(step * 3))
                        else:
                            step = min(_MAX_BLOCK_STEP, int(step * 2.5))

    def _fetch_block_range(
        self,
        address: str,
        from_block: int,
        to_block: int,
    ) -> tuple[list[DecodedEvent], bool]:
        """Fetch and decode all events in a block range.

        Returns:
            Tuple of (decoded_events, hit_record_limit).
        """
        raw_logs = self._client.get_logs(
            address=address,
            from_block=from_block,
            to_block=to_block,
        )

        hit_limit = len(raw_logs) >= _ETHERSCAN_MAX_RECORDS

        decoded: list[DecodedEvent] = []
        for raw in raw_logs:
            event = decode_log(raw)
            if event is not None:
                decoded.append(event)

        return decoded, hit_limit

    @staticmethod
    def _count_events(events: list[DecodedEvent]) -> dict[str, int]:
        """Count events by type name."""
        counts: dict[str, int] = {}
        for evt in events:
            name = type(evt).__name__.replace("Event", "").lower()
            counts[name] = counts.get(name, 0) + 1
        return counts

    def fetch_all(
        self,
        pairs: list[PairConfig],
        from_block: int,
        to_block: int,
        workers: Optional[int] = None,
    ) -> None:
        """Fetch events for all pairs. If workers > 1, run pairs in parallel (one key per call, no per-key overuse)."""
        if workers is None or workers <= 1:
            for pair in pairs:
                self.fetch_pair(pair, from_block, to_block)
            return

        n = min(workers, len(pairs))
        with ThreadPoolExecutor(max_workers=n) as executor:
            futures = {
                executor.submit(self.fetch_pair, pair, from_block, to_block): pair
                for pair in pairs
            }
            for fut in as_completed(futures):
                pair = futures[fut]
                try:
                    fut.result()
                except Exception:
                    logger.exception("Pair %s failed", pair.name)
                    raise
