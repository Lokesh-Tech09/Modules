"""
Custom exceptions for Module 3: Blockchain Upload & Verification.
"""


class BlockchainVerificationError(Exception):
    """Base exception for all Module 3 blockchain operations."""
    pass


class UnverifiedRecordError(BlockchainVerificationError):
    """Raised when an attempt is made to anchor an unverified or rejected record on-chain."""
    def __init__(self, status: str, message: str | None = None):
        msg = message or f"Cannot anchor record with non-verified status: '{status}'. Only 'verified' records are permitted."
        super().__init__(msg)
        self.status = status


class CanonicalizationError(BlockchainVerificationError):
    """Raised when record serialization or canonicalization fails."""
    pass


class ChainClientError(BlockchainVerificationError):
    """Base exception for blockchain client or network interaction failures."""
    pass


class ChainConnectionError(ChainClientError):
    """Raised when the blockchain RPC endpoint is unreachable or times out."""
    pass


class ChainTransactionError(ChainClientError):
    """Raised when a blockchain transaction fails, reverts, or runs out of gas."""
    def __init__(self, message: str, tx_hash: str | None = None):
        super().__init__(message)
        self.tx_hash = tx_hash


class RateLimitExceededError(BlockchainVerificationError):
    """Raised when on-chain writes exceed safe frequency or cost-guard limits."""
    pass


class RecordNotFoundError(BlockchainVerificationError):
    """Raised when a verification record cannot be located on-chain or off-chain."""
    def __init__(self, reference_id: str, location: str = "storage"):
        super().__init__(f"Record with reference_id '{reference_id}' was not found in {location}.")
        self.reference_id = reference_id
        self.location = location


class OffchainStoreError(BlockchainVerificationError):
    """Raised when an off-chain storage operation fails."""
    pass
