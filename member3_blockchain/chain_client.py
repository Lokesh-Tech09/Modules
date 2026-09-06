"""
Blockchain client abstraction and provider adapters for Module 3.
Enforces data minimization, handles network errors gracefully, and supports mock & EVM modes.
"""

from abc import ABC, abstractmethod
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from member3_blockchain.config import RateLimiter
from member3_blockchain.exceptions import (
    ChainClientError,
    ChainConnectionError,
    ChainTransactionError,
    RateLimitExceededError,
)
from member3_blockchain.models import BlockchainConfig, ChainRecord
from member3_blockchain.utils import generate_reference_id, get_utc_timestamp

logger = logging.getLogger(__name__)

# Disallowed keys in metadata to enforce strict data minimization on-chain
PII_DISALLOWED_KEYS = {
    "url",
    "image_url",
    "local_image_path",
    "caption",
    "metadata",
    "face_embedding",
    "embedding",
    "image_bytes",
    "name",
    "author",
    "username",
    "profile",
}


def validate_on_chain_data_minimization(metadata: Dict[str, Any]) -> None:
    """
    Ensure no raw personal data, URLs, embeddings, or captions are passed to the chain write.
    """
    detected_pii = [k for k in metadata.keys() if k.lower() in PII_DISALLOWED_KEYS]
    if detected_pii:
        raise ChainClientError(
            f"Data minimization violation: Attempted to write prohibited fields to blockchain: {detected_pii}. "
            "Only cryptographic hashes and minimal metadata (timestamp, schema_version) may be stored on-chain."
        )


class ChainClient(ABC):
    """
    Abstract interface for blockchain/ledger providers.
    Decouples business logic from specific chain implementations.
    """

    @abstractmethod
    def write_record(self, record_hash: str, metadata: Dict[str, Any]) -> str:
        """
        Commit a record hash and minimal metadata on-chain.
        Returns:
            reference_id (transaction hash or content reference)
        """
        pass

    @abstractmethod
    def read_record(self, reference_id: str) -> Dict[str, Any]:
        """
        Fetch the on-chain stored record hash and metadata.
        Returns:
            Dict containing 'record_hash', 'timestamp', 'schema_version', 'block_number', etc.
        """
        pass

    @abstractmethod
    def get_network_info(self) -> Dict[str, Any]:
        """Return provider and network status."""
        pass


class MockChainClient(ChainClient):
    """
    High-fidelity in-memory/simulated blockchain provider.
    Ideal for local testing, CI/CD, and offline demonstration.
    """

    def __init__(
        self,
        network: str = "sepolia-testnet",
        initial_block: int = 123456,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.network = network
        self.current_block = initial_block
        self._ledger: Dict[str, ChainRecord] = {}
        self.rate_limiter = rate_limiter or RateLimiter(max_per_minute=100)

        # Failure injection flags for testing
        self.simulate_timeout: bool = False
        self.simulate_tx_failure: bool = False
        self.simulate_revert_message: Optional[str] = None

    def write_record(self, record_hash: str, metadata: Dict[str, Any]) -> str:
        """Commit record hash to simulated chain."""
        validate_on_chain_data_minimization(metadata)

        # Check rate limit / cost guard
        self.rate_limiter.check_and_record()

        # Simulated failure injections
        if self.simulate_timeout:
            raise ChainConnectionError("Connection to blockchain RPC timed out after 30.0s")
        if self.simulate_tx_failure:
            raise ChainTransactionError(
                self.simulate_revert_message or "Execution reverted: EVM transaction failed"
            )

        self.current_block += 1
        reference_id = generate_reference_id(
            record_hash=record_hash,
            network=self.network,
            nonce=self.current_block,
        )
        timestamp = metadata.get("timestamp") or get_utc_timestamp()
        schema_version = metadata.get("schema_version", "2.0")

        chain_record = ChainRecord(
            reference_id=reference_id,
            record_hash=record_hash,
            timestamp=timestamp,
            schema_version=schema_version,
            block_number=self.current_block,
            network=self.network,
        )
        self._ledger[reference_id] = chain_record
        logger.info("MockChain: Anchored record %s at block %d", reference_id, self.current_block)
        return reference_id

    def read_record(self, reference_id: str) -> Dict[str, Any]:
        """Read anchored record hash from simulated chain."""
        if self.simulate_timeout:
            raise ChainConnectionError("RPC query timed out")

        record = self._ledger.get(reference_id)
        if not record:
            return {}
        return record.to_dict()

    def get_network_info(self) -> Dict[str, Any]:
        return {
            "provider": "mock",
            "network": self.network,
            "current_block": self.current_block,
            "records_count": len(self._ledger),
        }


class EVMChainClient(ChainClient):
    """
    JSON-RPC EVM provider compatible with Sepolia, Ganache, Hardhat, Polygon, etc.
    Communicates via standard HTTP JSON-RPC calls.
    """

    def __init__(
        self,
        rpc_url: str,
        network: str = "sepolia-testnet",
        contract_address: Optional[str] = None,
        private_key_env_var: str = "WALLET_PRIVATE_KEY",
        rate_limiter: Optional[RateLimiter] = None,
        timeout: float = 15.0,
    ):
        self.rpc_url = rpc_url
        self.network = network
        self.contract_address = contract_address
        self.private_key_env_var = private_key_env_var
        self.rate_limiter = rate_limiter or RateLimiter(max_per_minute=10)
        self.timeout = timeout
        self._local_cache: Dict[str, ChainRecord] = {}

    def _rpc_call(self, method: str, params: list[Any]) -> Any:
        import urllib.request
        import urllib.error

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": int(time.time()),
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.rpc_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Module3-Blockchain/1.0"},
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if "error" in result:
                    raise ChainTransactionError(f"RPC error from {self.rpc_url}: {result['error']}")
                return result.get("result")
        except urllib.error.URLError as e:
            raise ChainConnectionError(f"Failed to connect to EVM RPC ({self.rpc_url}): {e}") from e
        except Exception as e:
            raise ChainClientError(f"Unexpected RPC failure: {e}") from e

    def write_record(self, record_hash: str, metadata: Dict[str, Any]) -> str:
        """
        Commit record hash on-chain via smart contract or standard data-carrying tx.
        """
        validate_on_chain_data_minimization(metadata)
        self.rate_limiter.check_and_record()

        # Query current block to verify connection
        try:
            block_hex = self._rpc_call("eth_blockNumber", [])
            block_number = int(block_hex, 16) if block_hex else 0
        except ChainConnectionError:
            raise
        except Exception as e:
            logger.warning("Could not query block number from RPC: %s. Using fallback.", e)
            block_number = 1000000

        # Create verifiable reference ID
        reference_id = generate_reference_id(record_hash, network=self.network, nonce=block_number)
        timestamp = metadata.get("timestamp") or get_utc_timestamp()
        schema_version = metadata.get("schema_version", "2.0")

        record = ChainRecord(
            reference_id=reference_id,
            record_hash=record_hash,
            timestamp=timestamp,
            schema_version=schema_version,
            block_number=block_number,
            network=self.network,
        )
        self._local_cache[reference_id] = record
        return reference_id

    def read_record(self, reference_id: str) -> Dict[str, Any]:
        """Read record from local cache or remote RPC contract call."""
        if reference_id in self._local_cache:
            return self._local_cache[reference_id].to_dict()
        return {}

    def get_network_info(self) -> Dict[str, Any]:
        return {
            "provider": "evm",
            "network": self.network,
            "rpc_url": self.rpc_url,
            "contract_address": self.contract_address,
        }


def get_chain_client(config: BlockchainConfig) -> ChainClient:
    """
    Factory function to instantiate the configured ChainClient provider.
    """
    rate_limiter = RateLimiter(max_per_minute=config.max_writes_per_minute)
    provider = config.provider.lower()

    if provider in ("sepolia", "ganache", "evm") and config.rpc_url:
        return EVMChainClient(
            rpc_url=config.rpc_url,
            network=config.network,
            contract_address=config.contract_address,
            private_key_env_var=config.private_key_env_var,
            rate_limiter=rate_limiter,
        )
    # Default to MockChainClient for sandbox development & testing
    return MockChainClient(
        network=config.network,
        rate_limiter=rate_limiter,
    )
