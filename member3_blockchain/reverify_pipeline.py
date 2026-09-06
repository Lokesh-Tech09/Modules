"""
Re-verification pipeline for Module 3: Blockchain Upload & Verification.
Performs tamper detection by recomputing cryptographic fingerprints and comparing against on-chain anchors.
"""

import logging
from typing import Any, Dict, Optional

from member3_blockchain.chain_client import ChainClient, get_chain_client
from member3_blockchain.config import load_config_from_env
from member3_blockchain.hasher import hash_verification_record
from member3_blockchain.models import BlockchainConfig, ReverificationResult
from member3_blockchain.offchain_store import OffchainStore

logger = logging.getLogger(__name__)


class ReverificationPipeline:
    """
    Orchestration service for verifying the tamper-evident integrity of verification records.
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

    def process(
        self,
        reference_id: str,
        current_verification_result: Optional[Dict[str, Any]] = None,
    ) -> ReverificationResult:
        """
        Execute the 6-step re-verification flow:
        1. Accept reference_id and optional current_verification_result.
        2. Fetch original record from offchain_store using reference_id.
        3. Fetch on-chain hash via chain_client.read_record(reference_id).
        4. Recompute the hash of the record using identical canonicalization.
        5. Compare recomputed hash to on-chain hash.
        6. Return ReverificationResult: 'intact' | 'tampered' | 'not_found'.
        """
        # STEP 1 & 2: Fetch stored off-chain record
        stored_record = self.offchain_store.get_record(reference_id)
        
        # Determine the target record to inspect:
        # If caller passed a current record, test that; otherwise test the stored off-chain record.
        target_record = current_verification_result if current_verification_result is not None else stored_record

        # STEP 3: Fetch on-chain record
        onchain_record = self.chain_client.read_record(reference_id)
        on_chain_hash = onchain_record.get("record_hash")

        # Guard: Check if reference_id exists in both places
        if not on_chain_hash or target_record is None:
            logger.warning(
                "Record not found during re-verification: reference_id=%s (on_chain=%s, record_found=%s)",
                reference_id,
                bool(on_chain_hash),
                target_record is not None,
            )
            return ReverificationResult(
                status="not_found",
                reference_id=reference_id,
                on_chain_hash=on_chain_hash,
                recomputed_hash=None,
                match=False,
            )

        # STEP 4: Recompute cryptographic fingerprint using canonicalization
        hash_result = hash_verification_record(target_record)
        recomputed_hash = hash_result.record_hash

        # STEP 5 & 6: Compare hashes for tamper detection
        is_match = (recomputed_hash.lower() == on_chain_hash.lower())

        if is_match:
            logger.info("Re-verification SUCCESS: Record %s is intact", reference_id)
            return ReverificationResult(
                status="intact",
                reference_id=reference_id,
                on_chain_hash=on_chain_hash,
                recomputed_hash=recomputed_hash,
                match=True,
            )
        else:
            logger.warning(
                "TAMPER DETECTED for record %s! On-chain: %s, Recomputed: %s",
                reference_id,
                on_chain_hash,
                recomputed_hash,
            )
            return ReverificationResult(
                status="tampered",
                reference_id=reference_id,
                on_chain_hash=on_chain_hash,
                recomputed_hash=recomputed_hash,
                match=False,
            )


def reverify_record(
    reference_id: str,
    current_verification_result: Optional[Dict[str, Any]] = None,
    *,
    config: Optional[BlockchainConfig] = None,
    chain_client: Optional[ChainClient] = None,
    offchain_store: Optional[OffchainStore] = None,
) -> ReverificationResult:
    """
    Public entrypoint to verify record integrity against the blockchain anchor.

    Args:
        reference_id: Blockchain transaction ID / content ID from upload.
        current_verification_result: Optional candidate record. If omitted, checks
                                     the record stored in the local off-chain database.
        config: Optional BlockchainConfig override.
        chain_client: Optional ChainClient provider override.
        offchain_store: Optional OffchainStore override.

    Returns:
        ReverificationResult: status ('intact' | 'tampered' | 'not_found') and hashes.
    """
    pipeline = ReverificationPipeline(
        config=config,
        chain_client=chain_client,
        offchain_store=offchain_store,
    )
    return pipeline.process(
        reference_id=reference_id,
        current_verification_result=current_verification_result,
    )
