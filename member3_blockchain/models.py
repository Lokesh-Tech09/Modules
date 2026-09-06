"""
Data models for Module 3: Blockchain Upload & Verification.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ChainMetadata(BaseModel):
    """Metadata regarding on-chain confirmation of the record."""
    network: str = "sepolia-testnet"
    confirmed: bool = True
    block_number: int = 0
    tx_hash: Optional[str] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "network": self.network,
            "confirmed": self.confirmed,
            "block_number": self.block_number,
        }
        if self.tx_hash:
            data["tx_hash"] = self.tx_hash
        if self.timestamp:
            data["timestamp"] = self.timestamp
        return data


class UploadResult(BaseModel):
    """
    Contract output for upload_verification_record.
    Matches Section 10 of Module 3 specifications.
    """
    status: str = "uploaded"
    reference_id: str
    record_hash: str
    chain: ChainMetadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reference_id": self.reference_id,
            "record_hash": self.record_hash,
            "chain": self.chain.to_dict(),
        }


class ReverificationResult(BaseModel):
    """
    Contract output for reverify_record.
    Matches Section 10 of Module 3 specifications.
    Status can be: 'intact' | 'tampered' | 'not_found'
    """
    status: str
    reference_id: str
    on_chain_hash: Optional[str] = None
    recomputed_hash: Optional[str] = None
    match: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reference_id": self.reference_id,
            "on_chain_hash": self.on_chain_hash,
            "recomputed_hash": self.recomputed_hash,
            "match": self.match,
        }


class CanonicalHashResult(BaseModel):
    """Result of canonicalizing and hashing a verification record."""
    record_hash: str
    canonical_json: str
    algorithm: str = "sha256"
    timestamp: str


class ChainRecord(BaseModel):
    """Minimal immutable record stored on-chain (Strict Data Minimization)."""
    reference_id: str
    record_hash: str
    timestamp: str
    schema_version: str = "2.0"
    block_number: int
    network: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "record_hash": self.record_hash,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
            "block_number": self.block_number,
            "network": self.network,
        }


class BlockchainConfig(BaseModel):
    """Configuration for blockchain interaction, providers, and storage."""
    provider: str = Field(default="mock", description="Chain provider: mock | sepolia | ganache | evm")
    network: str = Field(default="sepolia-testnet", description="Network identifier name")
    rpc_url: Optional[str] = Field(default="https://rpc.sepolia.org", description="JSON-RPC endpoint")
    contract_address: Optional[str] = Field(default=None, description="Anchor smart contract address")
    private_key_env_var: str = Field(default="WALLET_PRIVATE_KEY", description="Env variable holding wallet key")
    max_writes_per_minute: int = Field(default=10, description="Rate limit / cost guard writes per minute")
    offchain_store_path: str = Field(default="member3_blockchain/offchain_store.db", description="SQLite DB path")
    enforce_data_minimization: bool = Field(default=True, description="Enforce no PII on chain")
