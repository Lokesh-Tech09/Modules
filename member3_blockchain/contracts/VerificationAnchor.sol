// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title VerificationAnchor
 * @dev Anchors cryptographic fingerprints (SHA-256) of identity verification records on-chain.
 * Enforces strict data minimization: stores only the record hash, timestamp, and schema version.
 * Absolutely NO PII, image bytes, embeddings, or URLs are ever accepted or stored.
 */
contract VerificationAnchor {
    
    struct AnchorRecord {
        bytes32 recordHash;
        uint256 timestamp;
        string schemaVersion;
        address recorder;
        bool exists;
    }

    // Mapping from unique referenceId (bytes32) to AnchorRecord
    mapping(bytes32 => AnchorRecord) private records;

    // Event emitted upon successful record anchoring
    event RecordAnchored(
        bytes32 indexed referenceId,
        bytes32 indexed recordHash,
        uint256 timestamp,
        string schemaVersion,
        address recorder
    );

    /**
     * @notice Anchor a verified record hash on the blockchain.
     * @param referenceId Deterministic reference ID (e.g. keccak256 or sha256 of hash+nonce)
     * @param recordHash The SHA-256 cryptographic digest of the canonical verification record
     * @param schemaVersion Schema version string (e.g. "2.0")
     */
    function anchorRecord(
        bytes32 referenceId,
        bytes32 recordHash,
        string calldata schemaVersion
    ) external {
        require(recordHash != bytes32(0), "Invalid record hash: cannot be zero");
        require(!records[referenceId].exists, "Record already anchored with this referenceId");

        records[referenceId] = AnchorRecord({
            recordHash: recordHash,
            timestamp: block.timestamp,
            schemaVersion: schemaVersion,
            recorder: msg.sender,
            exists: true
        });

        emit RecordAnchored(
            referenceId,
            recordHash,
            block.timestamp,
            schemaVersion,
            msg.sender
        );
    }

    /**
     * @notice Retrieve an anchored record by its referenceId for integrity re-verification.
     * @param referenceId The reference ID to lookup
     */
    function getRecord(bytes32 referenceId)
        external
        view
        returns (
            bytes32 recordHash,
            uint256 timestamp,
            string memory schemaVersion,
            address recorder,
            bool exists
        )
    {
        AnchorRecord memory rec = records[referenceId];
        return (
            rec.recordHash,
            rec.timestamp,
            rec.schemaVersion,
            rec.recorder,
            rec.exists
        );
    }

    /**
     * @notice Verify whether a candidate hash matches the on-chain anchor.
     * @param referenceId The reference ID
     * @param candidateHash The recomputed SHA-256 hash
     * @return isIntact True if candidateHash matches anchored hash exactly
     */
    function verifyIntegrity(bytes32 referenceId, bytes32 candidateHash)
        external
        view
        returns (bool isIntact)
    {
        AnchorRecord memory rec = records[referenceId];
        if (!rec.exists) {
            return false;
        }
        return rec.recordHash == candidateHash;
    }
}
