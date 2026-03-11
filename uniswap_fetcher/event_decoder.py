"""Decoder for UniswapV2 event logs returned by Etherscan getLogs API."""

import logging
from typing import Any, Optional, Union

from eth_abi import decode

from .models import (
    BURN_TOPIC,
    MINT_TOPIC,
    SWAP_TOPIC,
    SYNC_TOPIC,
    BurnEvent,
    MintEvent,
    SwapEvent,
    SyncEvent,
)

logger = logging.getLogger(__name__)

DecodedEvent = Union[SwapEvent, SyncEvent, MintEvent, BurnEvent]


def _hex_to_int(hex_str: str) -> int:
    """Convert a hex string (with or without 0x prefix) to int.

    Etherscan sometimes returns bare '0x' to represent zero.
    """
    if hex_str in ("0x", "0X", ""):
        return 0
    return int(hex_str, 16)


def _pad_address(topic_hex: str) -> str:
    """Extract a 20-byte address from a 32-byte topic value."""
    return "0x" + topic_hex[-40:]


def decode_log(raw_log: dict[str, Any]) -> Optional[DecodedEvent]:
    """Decode a single raw Etherscan log entry into a typed event.

    Args:
        raw_log: A dict from Etherscan getLogs response containing
                 'topics', 'data', 'blockNumber', 'transactionHash', etc.

    Returns:
        A decoded event dataclass, or None if the topic is unrecognised.
    """
    topics = raw_log.get("topics", [])
    if not topics:
        return None

    topic0 = topics[0].lower()
    data_hex = raw_log.get("data", "0x")
    data_bytes = bytes.fromhex(data_hex[2:]) if len(data_hex) > 2 else b""

    block_number = _hex_to_int(raw_log["blockNumber"])
    tx_hash = raw_log["transactionHash"]
    tx_index = _hex_to_int(raw_log["transactionIndex"])
    log_index = _hex_to_int(raw_log["logIndex"])
    timestamp = _hex_to_int(raw_log["timeStamp"])
    gas_price = _hex_to_int(raw_log.get("gasPrice", "0x0"))

    try:
        if topic0 == SWAP_TOPIC:
            return _decode_swap(
                block_number, tx_hash, tx_index, log_index,
                timestamp, gas_price, topics, data_bytes,
            )
        if topic0 == SYNC_TOPIC:
            return _decode_sync(
                block_number, tx_hash, tx_index, log_index,
                timestamp, data_bytes,
            )
        if topic0 == MINT_TOPIC:
            return _decode_mint(
                block_number, tx_hash, tx_index, log_index,
                timestamp, topics, data_bytes,
            )
        if topic0 == BURN_TOPIC:
            return _decode_burn(
                block_number, tx_hash, tx_index, log_index,
                timestamp, topics, data_bytes,
            )
    except Exception:
        logger.exception(
            "Failed to decode event topic0=%s tx=%s log_index=%d",
            topic0[:10], tx_hash, log_index,
        )
        return None

    return None


def _decode_swap(
    block_number: int,
    tx_hash: str,
    tx_index: int,
    log_index: int,
    timestamp: int,
    gas_price: int,
    topics: list[str],
    data_bytes: bytes,
) -> SwapEvent:
    """Decode Swap(address indexed sender, uint256, uint256, uint256, uint256, address indexed to)."""
    sender = _pad_address(topics[1])
    to = _pad_address(topics[2])
    amount0_in, amount1_in, amount0_out, amount1_out = decode(
        ["uint256", "uint256", "uint256", "uint256"], data_bytes,
    )
    return SwapEvent(
        block_number=block_number,
        tx_hash=tx_hash,
        tx_index=tx_index,
        log_index=log_index,
        timestamp=timestamp,
        sender=sender,
        to=to,
        amount0_in=amount0_in,
        amount1_in=amount1_in,
        amount0_out=amount0_out,
        amount1_out=amount1_out,
        gas_price=gas_price,
    )


def _decode_sync(
    block_number: int,
    tx_hash: str,
    tx_index: int,
    log_index: int,
    timestamp: int,
    data_bytes: bytes,
) -> SyncEvent:
    """Decode Sync(uint112 reserve0, uint112 reserve1)."""
    reserve0, reserve1 = decode(["uint112", "uint112"], data_bytes)
    return SyncEvent(
        block_number=block_number,
        tx_hash=tx_hash,
        tx_index=tx_index,
        log_index=log_index,
        timestamp=timestamp,
        reserve0=reserve0,
        reserve1=reserve1,
    )


def _decode_mint(
    block_number: int,
    tx_hash: str,
    tx_index: int,
    log_index: int,
    timestamp: int,
    topics: list[str],
    data_bytes: bytes,
) -> MintEvent:
    """Decode Mint(address indexed sender, uint256 amount0, uint256 amount1)."""
    sender = _pad_address(topics[1])
    amount0, amount1 = decode(["uint256", "uint256"], data_bytes)
    return MintEvent(
        block_number=block_number,
        tx_hash=tx_hash,
        tx_index=tx_index,
        log_index=log_index,
        timestamp=timestamp,
        sender=sender,
        amount0=amount0,
        amount1=amount1,
    )


def _decode_burn(
    block_number: int,
    tx_hash: str,
    tx_index: int,
    log_index: int,
    timestamp: int,
    topics: list[str],
    data_bytes: bytes,
) -> BurnEvent:
    """Decode Burn(address indexed sender, uint256, uint256, address indexed to)."""
    sender = _pad_address(topics[1])
    to = _pad_address(topics[2])
    amount0, amount1 = decode(["uint256", "uint256"], data_bytes)
    return BurnEvent(
        block_number=block_number,
        tx_hash=tx_hash,
        tx_index=tx_index,
        log_index=log_index,
        timestamp=timestamp,
        sender=sender,
        to=to,
        amount0=amount0,
        amount1=amount1,
    )
