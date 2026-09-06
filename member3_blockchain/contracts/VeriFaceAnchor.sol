// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title VeriFaceAnchor
 * @dev Anchors canonical SHA-256 fingerprints of verified facial identity records
 *      onto the Ethereum blockchain (e.g. Sepolia testnet).
 *      No PII, biometric data, or raw images are stored on-chain (GDPR data minimization).
 */
contract VeriFaceAnchor {
    struct AnchorRecord {
        bytes32 recordHash;     // SHA-256 canonical fingerprint
        uint256 blockTimestamp; // On-chain block timestamp
        uint256 blockNumber;    // On-chain block height
        address anchoredBy;     // Address submitting the transaction
        string metadataUri;     // Optional IPFS or off-chain reference URI
    }

    // Mapping from referenceId (or transaction UUID) to AnchorRecord
    mapping(string => AnchorRecord) private records;

    // Reverse lookup: check if a hash has already been anchored
    mapping(bytes32 => bool) private anchoredHashes;

    // Contract owner
    address public owner;

    // Events
    event RecordAnchored(
        string indexed referenceId,
        bytes32 indexed recordHash,
        uint256 blockTimestamp,
        uint256 blockNumber,
        address indexed anchoredBy
    );

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "VeriFaceAnchor: caller is not the owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Anchor a verified record's canonical SHA-256 fingerprint on-chain.
     * @param referenceId Unique reference identifier for the verification session.
     * @param recordHash The 32-byte SHA-256 hash of the canonical verification payload.
     * @param metadataUri Optional off-chain metadata link (e.g. ipfs:// or sqlite ref).
     */
    function anchorRecord(
        string calldata referenceId,
        bytes32 recordHash,
        string calldata metadataUri
    ) external {
        require(bytes(referenceId).length > 0, "VeriFaceAnchor: referenceId cannot be empty");
        require(recordHash != bytes32(0), "VeriFaceAnchor: recordHash cannot be empty");
        require(records[referenceId].blockTimestamp == 0, "VeriFaceAnchor: record already exists");

        records[referenceId] = AnchorRecord({
            recordHash: recordHash,
            blockTimestamp: block.timestamp,
            blockNumber: block.number,
            anchoredBy: msg.sender,
            metadataUri: metadataUri
        });

        anchoredHashes[recordHash] = true;

        emit RecordAnchored(
            referenceId,
            recordHash,
            block.timestamp,
            block.number,
            msg.sender
        );
    }

    /**
     * @notice Retrieve an anchored record by referenceId.
     * @param referenceId The unique reference ID.
     */
    function getRecord(string calldata referenceId)
        external
        view
        returns (
            bytes32 recordHash,
            uint256 blockTimestamp,
            uint256 blockNumber,
            address anchoredBy,
            string memory metadataUri
        )
    {
        AnchorRecord memory rec = records[referenceId];
        require(rec.blockTimestamp > 0, "VeriFaceAnchor: record not found");
        return (
            rec.recordHash,
            rec.blockTimestamp,
            rec.blockNumber,
            rec.anchoredBy,
            rec.metadataUri
        );
    }

    /**
     * @notice Verify whether a given recordHash matches the on-chain anchor for referenceId.
     * @param referenceId The reference ID to check.
     * @param recordHash The recomputed canonical SHA-256 hash to compare.
     * @return matches True if hashes match exactly, False if tampered or missing.
     */
    function verifyHash(string calldata referenceId, bytes32 recordHash)
        external
        view
        returns (bool matches)
    {
        if (records[referenceId].blockTimestamp == 0) {
            return false;
        }
        return records[referenceId].recordHash == recordHash;
    }

    /**
     * @notice Check if a specific hash exists on-chain anywhere.
     */
    function isHashAnchored(bytes32 recordHash) external view returns (bool) {
        return anchoredHashes[recordHash];
    }
}
