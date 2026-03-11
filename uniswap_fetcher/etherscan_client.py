"""Etherscan API V2 client with retry logic."""

import logging
import time
from typing import Any, Optional

import requests

from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.etherscan.io/v2/api"
_MAX_RETRIES = 5
_RETRY_BACKOFF_BASE = 2.0


class EtherscanAPIError(Exception):
    """Raised when Etherscan returns an error response."""


class EtherscanClient:
    """Thin wrapper around Etherscan API V2 with automatic rate limiting."""

    def __init__(
        self,
        rate_limiter: RateLimiter,
        chain_id: int = 1,
        timeout: int = 30,
    ) -> None:
        self._limiter = rate_limiter
        self._chain_id = chain_id
        self._timeout = timeout
        self._session = requests.Session()

    def _request(self, params: dict[str, Any]) -> Any:
        """Execute a rate-limited request with exponential-backoff retry.

        Returns the 'result' field from the Etherscan JSON response.
        """
        params["chainid"] = str(self._chain_id)

        for attempt in range(1, _MAX_RETRIES + 1):
            api_key = self._limiter.acquire()
            params["apikey"] = api_key

            try:
                resp = self._session.get(
                    _BASE_URL, params=params, timeout=self._timeout,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                wait = _RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "HTTP error (attempt %d/%d): %s. Retrying in %.1fs.",
                    attempt, _MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
                continue

            data = resp.json()

            if data.get("status") == "1" or data.get("jsonrpc"):
                return data.get("result", data)

            message = data.get("message", "")
            result = data.get("result", "")

            result_str = str(result)
            message_str = str(message)
            if ("Max rate limit reached" in result_str
                    or "Max calls per sec" in result_str):
                wait = _RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "Rate limit hit (attempt %d/%d). Backing off %.1fs.",
                    attempt, _MAX_RETRIES, wait,
                )
                time.sleep(wait)
                continue
            if ("timeout" in message_str.lower()
                    or "server too busy" in message_str.lower()):
                wait = _RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "Etherscan busy/timeout (attempt %d/%d). Retrying in %.1fs.",
                    attempt, _MAX_RETRIES, wait,
                )
                time.sleep(wait)
                continue

            if "No records found" in message or result == []:
                return []

            raise EtherscanAPIError(
                f"Etherscan error: message={message}, result={result}"
            )

        raise EtherscanAPIError(
            f"Failed after {_MAX_RETRIES} retries. Last params: "
            f"module={params.get('module')}, action={params.get('action')}"
        )

    def get_logs(
        self,
        address: str,
        from_block: int,
        to_block: int,
        topic0: Optional[str] = None,
        page: int = 1,
        offset: int = 1000,
    ) -> list[dict[str, Any]]:
        """Fetch event logs for an address within a block range.

        Args:
            address: Contract address to query.
            from_block: Starting block number (inclusive).
            to_block: Ending block number (inclusive).
            topic0: Optional first topic filter (event signature hash).
            page: Page number for pagination.
            offset: Records per page (max 1000).

        Returns:
            List of raw log dicts from Etherscan.
        """
        params: dict[str, Any] = {
            "module": "logs",
            "action": "getLogs",
            "address": address,
            "fromBlock": str(from_block),
            "toBlock": str(to_block),
            "page": str(page),
            "offset": str(offset),
        }
        if topic0:
            params["topic0"] = topic0
        result = self._request(params)
        if isinstance(result, list):
            return result
        return []

    def get_block_number_by_timestamp(
        self,
        timestamp: int,
        closest: str = "before",
    ) -> int:
        """Get the block number closest to a given Unix timestamp.

        Args:
            timestamp: Unix timestamp in seconds.
            closest: Either 'before' or 'after'.

        Returns:
            Block number as integer.
        """
        params = {
            "module": "block",
            "action": "getblocknobytime",
            "timestamp": str(timestamp),
            "closest": closest,
        }
        result = self._request(params)
        return int(result)

    def get_latest_block_number(self) -> int:
        """Get the latest block number on chain."""
        params = {
            "module": "proxy",
            "action": "eth_blockNumber",
        }
        result = self._request(params)
        return int(result, 16)

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()
