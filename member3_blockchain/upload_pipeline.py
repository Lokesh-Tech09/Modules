"""
Upload pipeline for Module 3: Blockchain Upload & Verification.
Orchestrates validation, canonical hashing, minimal on-chain write, and off-chain persistence.
"""

import logging
from typing import Any, Dict, Optional

from member3_blockchain.chain_client import ChainClient, get_chain_client
from member3_blockchain.config import load_config_from_env
from member3_blockchain.exceptions import (
    ChainClientError,
    OffchainStoreError,
    UnverifiedRecordError,
)
from member3_blockchain.hasher import hash_verification_record
from member3_blockchain.models import BlockchainConfig, ChainMetadata, UploadResult
from member3_blockchain.offchain_store import OffchainStore

logger = logging.getLogger(__name__)


class UploadPipeline:
    """
    Orchestration service for anchoring verified records on blockchain.
    """

    def __init__(
        self,
        config: Optional[BlockchainConfig] = None,
        chain_client: Optional[ChainClient] = None,
        offchain_store: Optional[OffchainStore] = None,
    ):
        self.config = config or load_config_from_env()
        self.chain_client = chain_client or get_chain_client(self.config)
        self.offchain_store = offchain_store or OffchainStore(self.config.offchain_store_path)

    def process(self, verification_result: Dict[str, Any]) -> UploadResult:
        """
        Execute the 6-step upload flow:
        1. Validate input status == 'verified'
        2. Canonicalize and hash the verification record
        3. Write hash + minimal metadata (timestamp, schema_version) on-chain
        4. Receive reference_id from chain client
        5. Store full record off-chain, keyed by reference_id
        6. Return UploadResult

        Raises:
            UnverifiedRecordError: If status != 'verified'
            ChainClientError: If on-chain write fails
            OffchainStoreError: If off-chain store fails
        """
        # STEP 1: Guardrail — Only anchor verified records
        status = verification_result.get("status")
        if status != "verified":
            logger.warning("Upload rejected: verification status is '%s'", status)
            raise UnverifiedRecordError(status=status or "unknown")

        # STEP 2: Canonicalize and hash the record (deterministic SHA-256)
        hash_result = hash_verification_record(verification_result)
        record_hash = hash_result.record_hash
        timestamp = hash_result.timestamp
        schema_version = verification_result.get("schema_version", "2.0")

        # STEP 3 & 4: Write hash + MINIMAL metadata on-chain (Strict Data Minimization)
        # Never send images, embeddings, URLs, or captions to the blockchain
        onchain_metadata = {
            "timestamp": timestamp,
            "schema_version": schema_version,
        }

        try:
            reference_id = self.chain_client.write_record(
                record_hash=record_hash,
                metadata=onchain_metadata,
            )
        except Exception as e:
            logger.error("Failed to commit record hash to blockchain: %s", e)
            raise

        # Query block number / confirmation info from chain
        onchain_info = self.chain_client.read_record(reference_id)
        block_number = onchain_info.get("block_number", 0)

        # STEP 5: Store full record off-chain, keyed by reference_id
        try:
            self.offchain_store.save_record(
                reference_id=reference_id,
                record=verification_result,
                record_hash=record_hash,
            )
        except Exception as e:
            logger.error("Failed to persist off-chain record for %s: %s", reference_id, e)
            raise

        # STEP 6: Return structured UploadResult
        chain_meta = ChainMetadata(
            network=self.config.network,
            confirmed=True,
            block_number=block_number,
            tx_hash=reference_id,
            timestamp=timestamp,
        )

        return UploadResult(
            status="uploaded",
            reference_id=reference_id,
            record_hash=record_hash,
            chain=chain_meta,
        )


def upload_verification_record(
    verification_result: Dict[str, Any],
    *,
    config: Optional[BlockchainConfig] = None,
    chain_client: Optional[ChainClient] = None,
    offchain_store: Optional[OffchainStore] = None,
) -> UploadResult:
    """
    Public entrypoint to upload a verified record to the blockchain.

    Args:
        verification_result: Result dict from Module 2 (must have status == 'verified').
        config: Optional BlockchainConfig override.
        chain_client: Optional ChainClient provider override (useful for testing).
        offchain_store: Optional OffchainStore override (useful for testing).

    Returns:
        UploadResult containing reference_id, record_hash, and chain confirmation.
    """
    pipeline = UploadPipeline(
        config=config,
        chain_client=chain_client,
        offchain_store=offchain_store,
    )
    return pipeline.process(verification_result)
