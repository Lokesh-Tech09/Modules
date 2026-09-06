"""
Module 3: Blockchain Upload & Verification
Face Identification & Blockchain Verification Pipeline

Provides cryptographic hashing, immutable ledger anchoring, private off-chain storage,
and tamper-evident re-verification under strict data minimization rules.
"""

from member3_blockchain.chain_client import (
    ChainClient,
    EVMChainClient,
    MockChainClient,
    get_chain_client,
)
from member3_blockchain.config import RateLimiter, load_config_from_env
from member3_blockchain.exceptions import (
    BlockchainVerificationError,
    CanonicalizationError,
    ChainClientError,
    ChainConnectionError,
    ChainTransactionError,
    OffchainStoreError,
    RateLimitExceededError,
    RecordNotFoundError,
    UnverifiedRecordError,
)
from member3_blockchain.hasher import (
    canonicalize_verification_record,
    hash_verification_record,
)
from member3_blockchain.models import (
    BlockchainConfig,
    CanonicalHashResult,
    ChainMetadata,
    ChainRecord,
    ReverificationResult,
    UploadResult,
)
from member3_blockchain.deploy_contract import compile_contract, deploy_contract
from member3_blockchain.offchain_store import OffchainStore
from member3_blockchain.reverify_pipeline import ReverificationPipeline, reverify_record
from member3_blockchain.upload_pipeline import UploadPipeline, upload_verification_record

__version__ = "2.0.0"

__all__ = [
    # Pipelines & Core Functions
    "upload_verification_record",
    "reverify_record",
    "UploadPipeline",
    "ReverificationPipeline",
    "deploy_contract",
    "compile_contract",
    # Models & Configuration
    "BlockchainConfig",
    "UploadResult",
    "ReverificationResult",
    "ChainMetadata",
    "CanonicalHashResult",
    "ChainRecord",
    "RateLimiter",
    "load_config_from_env",
    # Chain Clients & Storage
    "ChainClient",
    "MockChainClient",
    "EVMChainClient",
    "get_chain_client",
    "OffchainStore",
    # Cryptographic Hashing
    "hash_verification_record",
    "canonicalize_verification_record",
    # Exceptions
    "BlockchainVerificationError",
    "UnverifiedRecordError",
    "CanonicalizationError",
    "ChainClientError",
    "ChainConnectionError",
    "ChainTransactionError",
    "RateLimitExceededError",
    "RecordNotFoundError",
    "OffchainStoreError",
]
