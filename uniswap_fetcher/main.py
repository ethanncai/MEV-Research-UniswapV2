"""CLI entry point for the UniswapV2 historical data fetcher."""

import argparse
import logging
import sys
import warnings

# Suppress urllib3 OpenSSL warning on systems with LibreSSL
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from .config import FetcherConfig, load_api_keys
from .csv_writer import CSVWriter
from .error_log import get_warning_count_last_30s, setup_error_log
from .etherscan_client import EtherscanClient
from .fetcher import CheckpointManager, LogFetcher, PairConfig
from .rate_limiter import DailyLimitExhaustedError, RateLimiter

logger = logging.getLogger("uniswap_fetcher")


def _setup_logging(verbose: bool) -> None:
    """Configure logging. In non-verbose mode, console only shows CRITICAL (effectively progress only)."""
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)
    if not verbose:
        for h in logging.root.handlers:
            h.setLevel(logging.CRITICAL)


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
        "--static-step",
        action="store_true",
        help="Use a fixed block step (no adaptive growth/shrink); step = config block_step.",
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
        print("Querying latest block number...", file=sys.stderr)
        cfg.to_block = client.get_latest_block_number()
        print(f"Latest block: {cfg.to_block}", file=sys.stderr)

    if cfg.from_block is None:
        cfg.from_block = cfg.maximize_from_block
        print(
            f"Maximize mode: from block {cfg.from_block} to {cfg.to_block} "
            f"(using all {limiter.total_keys} key(s) until daily limits).",
            file=sys.stderr,
        )
    else:
        print(
            f"Block range: {cfg.from_block} to {cfg.to_block} "
            f"({limiter.total_keys} key(s)).",
            file=sys.stderr,
        )
    print(f"Warnings/errors: {cfg.error_log_file}", file=sys.stderr)

    setup_error_log(cfg.error_log_file)

    pairs = [
        PairConfig(address=p["address"], name=p["name"])
        for p in cfg.pairs
    ]

    checkpoint = CheckpointManager(cfg.checkpoint_file)
    if checkpoint.pair_count > 0:
        print(f"Loaded checkpoint with {checkpoint.pair_count} pair(s).", file=sys.stderr)
    print(
        f"Starting fetch for {len(pairs)} pair(s), blocks {cfg.from_block} -> {cfg.to_block}.",
        file=sys.stderr,
    )

    def on_pair_start(name: str, address: str) -> None:
        print(f"--- Processing pair: {name} ({address}) ---", file=sys.stderr)

    if args.static_step:
        print("Using static step (no adaptive step).", file=sys.stderr)
    csv_writer = CSVWriter(cfg.output_dir)
    fetcher = LogFetcher(
        client=client,
        csv_writer=csv_writer,
        checkpoint=checkpoint,
        block_step=cfg.block_step,
        get_warning_count=get_warning_count_last_30s,
        on_pair_start=on_pair_start,
        static_step=args.static_step,
    )
    # Default workers = min(pairs, keys) so we don't have more threads than keys (no pointless blocking)
    if cfg.workers is not None:
        workers = cfg.workers
    else:
        workers = min(len(pairs), limiter.total_keys)
    if workers > 1:
        print(
            f"Using {workers} workers for {len(pairs)} pair(s) ({limiter.total_keys} key(s)).",
            file=sys.stderr,
        )
    try:
        fetcher.fetch_all(pairs, cfg.from_block, cfg.to_block, workers=workers)
    except KeyboardInterrupt:
        print("Interrupted. Progress checkpointed.", file=sys.stderr)
    except DailyLimitExhaustedError:
        print(
            "All API keys exhausted for today. Progress saved. Run again tomorrow or add more keys.",
            file=sys.stderr,
        )
    except Exception:
        logger.exception("Fatal error during fetch.")
        sys.exit(1)
    finally:
        csv_writer.close()
        client.close()

    print(f"Done. Data: {cfg.output_dir}", file=sys.stderr)
    for stat in limiter.stats():
        print(
            f"  Key ...{stat['key_suffix']}: {stat['calls_today']} used, {stat['remaining']} left",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
