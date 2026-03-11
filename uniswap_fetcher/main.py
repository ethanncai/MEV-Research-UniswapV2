"""CLI entry point for the UniswapV2 historical data fetcher."""

import argparse
import logging
import sys
import warnings

# Suppress urllib3 OpenSSL warning on systems with LibreSSL
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from .config import FetcherConfig, load_api_keys
from .csv_writer import CSVWriter
from .etherscan_client import EtherscanClient
from .fetcher import CheckpointManager, LogFetcher, PairConfig
from .rate_limiter import DailyLimitExhaustedError, RateLimiter

logger = logging.getLogger("uniswap_fetcher")


def _setup_logging(verbose: bool) -> None:
    """Configure root logger with console handler."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch UniswapV2 historical event data from Etherscan.",
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to YAML config file (default: config.yaml).",
    )
    parser.add_argument(
        "--from-block", type=int, default=None,
        help="Override start block number.",
    )
    parser.add_argument(
        "--to-block", type=int, default=None,
        help="Override end block number (default: latest).",
    )
    parser.add_argument(
        "-M", "--maximize",
        action="store_true",
        help="Explicit maximize mode: from earliest block to latest (default when no --from-block/--to-block given).",
    )
    parser.add_argument(
        "--keys", default=None,
        help="Override path to API keys file.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging.",
    )
    return parser


def main() -> None:
    """Main entry point."""
    parser = _build_parser()
    args = parser.parse_args()
    _setup_logging(args.verbose)

    cfg = FetcherConfig.from_yaml(args.config)

    if args.keys:
        cfg.api_keys_file = args.keys
    if args.from_block is not None:
        cfg.from_block = args.from_block
    if args.to_block is not None:
        cfg.to_block = args.to_block

    api_keys = load_api_keys(cfg.api_keys_file)
    limiter = RateLimiter(
        api_keys=api_keys,
        calls_per_second=cfg.calls_per_second,
        daily_limit=cfg.daily_limit,
    )
    client = EtherscanClient(rate_limiter=limiter, chain_id=cfg.chain_id)

    if cfg.to_block is None:
        logger.info("Querying latest block number...")
        cfg.to_block = client.get_latest_block_number()
        logger.info("Latest block: %d", cfg.to_block)

    # Default = maximize: fetch from earliest to latest, use all API keys until daily limits
    if cfg.from_block is None:
        cfg.from_block = cfg.maximize_from_block
        logger.info(
            "Maximize mode: from block %d to %d (using all %d key(s) until daily limits).",
            cfg.from_block, cfg.to_block, limiter.total_keys,
        )
    else:
        logger.info("Block range: %d to %d", cfg.from_block, cfg.to_block)

    pairs = [
        PairConfig(address=p["address"], name=p["name"])
        for p in cfg.pairs
    ]

    checkpoint = CheckpointManager(cfg.checkpoint_file)
    csv_writer = CSVWriter(cfg.output_dir)

    fetcher = LogFetcher(
        client=client,
        csv_writer=csv_writer,
        checkpoint=checkpoint,
        block_step=cfg.block_step,
    )

    try:
        fetcher.fetch_all(pairs, cfg.from_block, cfg.to_block)
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Progress has been checkpointed.")
    except DailyLimitExhaustedError as e:
        logger.info(
            "All API keys exhausted for today. Progress saved. Run again tomorrow or add more keys in api_keys.txt."
        )
        logger.debug("Limit error: %s", e)
    except Exception:
        logger.exception("Fatal error during fetch.")
        sys.exit(1)
    finally:
        csv_writer.close()
        client.close()

    logger.info("Done. Data saved to: %s", cfg.output_dir)

    for stat in limiter.stats():
        logger.info(
            "Key ...%s: %d calls used, %d remaining.",
            stat["key_suffix"], stat["calls_today"], stat["remaining"],
        )


if __name__ == "__main__":
    main()
