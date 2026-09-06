"""
Configuration management and cost-guard/rate-limiter for Module 3.
"""

from collections import deque
import os
import time
from typing import Optional

from member3_blockchain.exceptions import RateLimitExceededError
from member3_blockchain.models import BlockchainConfig

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_config_from_env() -> BlockchainConfig:
    """
    Load BlockchainConfig from environment variables with sensible defaults.
    """
    provider = os.getenv("BLOCKCHAIN_PROVIDER", "mock").lower()
    network = os.getenv("BLOCKCHAIN_NETWORK", "sepolia-testnet")
    rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "https://rpc.sepolia.org")
    contract_address = os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS", None)
    private_key_env_var = os.getenv("BLOCKCHAIN_PRIVATE_KEY_ENV_VAR", "WALLET_PRIVATE_KEY")
    
    max_writes = int(os.getenv("MAX_WRITES_PER_MINUTE", "10"))
    offchain_path = os.getenv("OFFCHAIN_STORE_PATH", "member3_blockchain/offchain_store.db")

    return BlockchainConfig(
        provider=provider,
        network=network,
        rpc_url=rpc_url,
        contract_address=contract_address,
        private_key_env_var=private_key_env_var,
        max_writes_per_minute=max_writes,
        offchain_store_path=offchain_path,
    )


class RateLimiter:
    """
    In-memory sliding-window rate limiter / cost guard to protect against
    runaway on-chain transaction writes and unexpected network fees.
    """
    def __init__(self, max_per_minute: int = 10):
        self.max_per_minute = max_per_minute
        self.timestamps: deque[float] = deque()

    def check_and_record(self) -> None:
        """
        Record an attempted write.
        Raises RateLimitExceededError if limit is reached within 60 seconds.
        """
        now = time.time()
        # Evict timestamps older than 60 seconds
        while self.timestamps and now - self.timestamps[0] > 60.0:
            self.timestamps.popleft()

        if len(self.timestamps) >= self.max_per_minute:
            raise RateLimitExceededError(
                f"On-chain write rate limit exceeded: maximum {self.max_per_minute} writes per minute allowed. "
                "Cost guard triggered to prevent excessive gas spend."
            )

        self.timestamps.append(now)

    def reset(self) -> None:
        """Reset the rate limiter state (useful in tests)."""
        self.timestamps.clear()
