"""Configuration loading and validation."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import yaml

logger = logging.getLogger(__name__)

# Well-known UniswapV2 high-liquidity pairs on Ethereum mainnet
DEFAULT_PAIRS: list[dict[str, str]] = [
    {
        "address": "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc",
        "name": "WETH_USDC",
    },
    {
        "address": "0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852",
        "name": "WETH_USDT",
    },
    {
        "address": "0xA478c2975Ab1Ea89e8196811F51A7B7Ade33eB11",
        "name": "WETH_DAI",
    },
    {
        "address": "0xBb2b8038a1640196FbE3e38816F3e67Cba72D940",
        "name": "WETH_WBTC",
    },
    {
        "address": "0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f",
        "name": "USDC_USDT",
    },
]


@dataclass
class FetcherConfig:
    """Top-level configuration for the UniswapV2 data fetcher."""

    api_keys_file: str = "api_keys.txt"
    chain_id: int = 1
    output_dir: str = "data"
    checkpoint_file: str = "data/checkpoint.json"
    from_block: Optional[int] = None
    to_block: Optional[int] = None
    maximize_from_block: int = 10_000_835  # UniswapV2 factory deployment
    block_step: int = 2000
    calls_per_second: int = 3
    daily_limit: int = 100_000
    pairs: list[dict[str, str]] = field(default_factory=lambda: list(DEFAULT_PAIRS))

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "FetcherConfig":
        """Load configuration from a YAML file, falling back to defaults."""
        filepath = Path(path)
        if not filepath.exists():
            logger.warning(
                "Config file %s not found, using defaults.", filepath,
            )
            return cls()

        with open(filepath, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}

        return cls(
            api_keys_file=raw.get("api_keys_file", cls.api_keys_file),
            chain_id=raw.get("chain_id", cls.chain_id),
            output_dir=raw.get("output_dir", cls.output_dir),
            checkpoint_file=raw.get("checkpoint_file", cls.checkpoint_file),
            from_block=raw.get("from_block"),
            to_block=raw.get("to_block"),
            maximize_from_block=raw.get("maximize_from_block", cls.maximize_from_block),
            block_step=raw.get("block_step", cls.block_step),
            calls_per_second=raw.get("calls_per_second", cls.calls_per_second),
            daily_limit=raw.get("daily_limit", cls.daily_limit),
            pairs=raw.get("pairs", list(DEFAULT_PAIRS)),
        )


def load_api_keys(filepath: Union[str, Path]) -> list[str]:
    """Load API keys from a text file (one key per line).

    Blank lines and lines starting with '#' are ignored.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(
            f"API keys file not found: {path}. "
            f"Create it with one Etherscan API key per line."
        )
    keys: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                keys.append(stripped)
    if not keys:
        raise ValueError(f"No API keys found in {path}.")
    logger.info("Loaded %d API key(s) from %s.", len(keys), path)
    return keys
