"""Data models and event signature constants for UniswapV2 events."""

from dataclasses import dataclass, fields
from typing import ClassVar


# ---------------------------------------------------------------------------
# Event topic0 signatures — keccak256 of the canonical event signature.
# Pre-computed to avoid runtime dependency on keccak libraries.
# ---------------------------------------------------------------------------

SWAP_TOPIC: str = (
    "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
)
SYNC_TOPIC: str = (
    "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"
)
MINT_TOPIC: str = (
    "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f"
)
BURN_TOPIC: str = (
    "0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496"
)

TOPIC_TO_NAME: dict[str, str] = {
    SWAP_TOPIC: "swap",
    SYNC_TOPIC: "sync",
    MINT_TOPIC: "mint",
    BURN_TOPIC: "burn",
}

ALL_TOPICS: list[str] = [SWAP_TOPIC, SYNC_TOPIC, MINT_TOPIC, BURN_TOPIC]


# ---------------------------------------------------------------------------
# Event dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SwapEvent:
    """Decoded UniswapV2 Swap event."""

    block_number: int
    tx_hash: str
    tx_index: int
    log_index: int
    timestamp: int
    sender: str
    to: str
    amount0_in: int
    amount1_in: int
    amount0_out: int
    amount1_out: int
    gas_price: int

    CSV_HEADERS: ClassVar[list[str]] = [
        "block_number", "tx_hash", "tx_index", "log_index", "timestamp",
        "sender", "to", "amount0_in", "amount1_in",
        "amount0_out", "amount1_out", "gas_price",
    ]

    def to_row(self) -> list[str]:
        """Return a list of string values matching CSV_HEADERS order."""
        return [str(getattr(self, f.name)) for f in fields(self)]


@dataclass(frozen=True)
class SyncEvent:
    """Decoded UniswapV2 Sync event."""

    block_number: int
    tx_hash: str
    tx_index: int
    log_index: int
    timestamp: int
    reserve0: int
    reserve1: int

    CSV_HEADERS: ClassVar[list[str]] = [
        "block_number", "tx_hash", "tx_index", "log_index", "timestamp",
        "reserve0", "reserve1",
    ]

    def to_row(self) -> list[str]:
        """Return a list of string values matching CSV_HEADERS order."""
        return [str(getattr(self, f.name)) for f in fields(self)]


@dataclass(frozen=True)
class MintEvent:
    """Decoded UniswapV2 Mint event."""

    block_number: int
    tx_hash: str
    tx_index: int
    log_index: int
    timestamp: int
    sender: str
    amount0: int
    amount1: int

    CSV_HEADERS: ClassVar[list[str]] = [
        "block_number", "tx_hash", "tx_index", "log_index", "timestamp",
        "sender", "amount0", "amount1",
    ]

    def to_row(self) -> list[str]:
        """Return a list of string values matching CSV_HEADERS order."""
        return [str(getattr(self, f.name)) for f in fields(self)]


@dataclass(frozen=True)
class BurnEvent:
    """Decoded UniswapV2 Burn event."""

    block_number: int
    tx_hash: str
    tx_index: int
    log_index: int
    timestamp: int
    sender: str
    to: str
    amount0: int
    amount1: int

    CSV_HEADERS: ClassVar[list[str]] = [
        "block_number", "tx_hash", "tx_index", "log_index", "timestamp",
        "sender", "to", "amount0", "amount1",
    ]

    def to_row(self) -> list[str]:
        """Return a list of string values matching CSV_HEADERS order."""
        return [str(getattr(self, f.name)) for f in fields(self)]
