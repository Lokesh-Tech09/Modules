"""
Secure off-chain storage for full verification records using SQLite.
Keys full records by reference_id, enabling cryptographic re-verification.
"""

import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from member3_blockchain.exceptions import OffchainStoreError
from member3_blockchain.utils import get_utc_timestamp, secure_file_permissions

logger = logging.getLogger(__name__)


class OffchainStore:
    """
    SQLite-backed repository for private, off-chain storage of complete verification records.
    Enforces restricted access permissions on initialization.
    """

    def __init__(self, db_path: str = "member3_blockchain/offchain_store.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._is_memory = db_path == ":memory:"

        if not self._is_memory:
            path_obj = Path(db_path)
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            # Create file if it doesn't exist and secure permissions
            if not path_obj.exists():
                path_obj.touch()
            secure_file_permissions(path_obj)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create verification records table if not exists."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verification_records (
                    reference_id TEXT PRIMARY KEY,
                    record_hash TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_record_hash ON verification_records (record_hash)
            """)
            self._conn.commit()

    def save_record(
        self,
        reference_id: str,
        record: Dict[str, Any],
        record_hash: str,
    ) -> None:
        """
        Save the full verification record, keyed by reference_id.
        """
        if not reference_id:
            raise OffchainStoreError("Cannot save record with empty reference_id")

        try:
            record_json = json.dumps(record, ensure_ascii=False)
            created_at = get_utc_timestamp()
            schema_version = record.get("schema_version", "2.0")

            with self._lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO verification_records 
                    (reference_id, record_hash, record_json, created_at, schema_version)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (reference_id, record_hash, record_json, created_at, schema_version),
                )
                self._conn.commit()
            logger.info("Saved off-chain record for reference_id: %s", reference_id)
        except Exception as e:
            raise OffchainStoreError(f"Failed to save off-chain record {reference_id}: {e}") from e

    def get_record(self, reference_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the full verification record by reference_id.
        Returns None if record does not exist.
        """
        try:
            with self._lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "SELECT record_json FROM verification_records WHERE reference_id = ?",
                    (reference_id,),
                )
                row = cursor.fetchone()
                if row:
                    return json.loads(row["record_json"])
                return None
        except Exception as e:
            raise OffchainStoreError(f"Failed to retrieve off-chain record {reference_id}: {e}") from e

    def record_exists(self, reference_id: str) -> bool:
        """Check if a record exists in off-chain storage."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT 1 FROM verification_records WHERE reference_id = ?",
                (reference_id,),
            )
            return cursor.fetchone() is not None

    def list_records(self) -> List[Dict[str, Any]]:
        """List summary of all stored records."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT reference_id, record_hash, created_at, schema_version FROM verification_records ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def delete_record(self, reference_id: str) -> bool:
        """Delete a record from off-chain storage."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "DELETE FROM verification_records WHERE reference_id = ?",
                (reference_id,),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def close(self) -> None:
        """Close the SQLite database connection."""
        with self._lock:
            self._conn.close()
