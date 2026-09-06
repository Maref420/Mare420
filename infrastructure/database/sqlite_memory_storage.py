"""SQLite-backed persistent storage for validated memory records.

Governed by: contracts/schemas/memory/memory-contract-v1.json
All database operations include error handling and graceful degradation.
Fallback implementation using stdlib sqlite3.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from intelligence.memory_system.models.memory_record import MemoryRecord
from intelligence.memory_system.storage.interface import MemoryStorage

logger = logging.getLogger(__name__)


class SqliteMemoryStorage(MemoryStorage):
    """SQLite-backed persistent storage for validated memory records.

    Governed: All operations fail gracefully with logging.
    Connection errors never propagate to callers.
    Thread-safe via check_same_thread=False.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or os.environ.get("ATLAS_MEMORY_DB", "./data/memory.db")
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._ensure_directory()
        self._connect()

    def _ensure_directory(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> None:
        try:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._init_schema()
        except Exception as e:
            logger.error("Failed to initialize SQLite connection", exc_info=e)
            self._conn = None

    def _init_schema(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_records (
                    memory_id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    validation_status TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL
                )
            """)
            self._conn.commit()
        except Exception as e:
            logger.error("Failed to initialize schema", exc_info=e)

    def store(self, record: MemoryRecord) -> None:
        if self._conn is None:
            logger.error("Connection not available, cannot store record")
            return
        try:
            self._lock.acquire()
            payload = (
                record.memory_id,
                record.memory_type.value,
                record.created_at.isoformat(),
                json.dumps(record.content),
                json.dumps(record.metadata),
                record.validation_status.value,
                record.operation_id,
                record.agent_id,
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO memory_records "
                "(memory_id, memory_type, created_at, content, metadata, "
                "validation_status, operation_id, agent_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                payload,
            )
            self._conn.commit()
        except Exception as e:
            logger.error("Failed to store memory record", exc_info=e)
        finally:
            self._lock.release()

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        if self._conn is None:
            logger.error("Connection not available, cannot retrieve record")
            return None
        try:
            self._lock.acquire()
            cursor = self._conn.execute(
                "SELECT memory_id, memory_type, created_at, content, "
                "metadata, validation_status, operation_id, agent_id "
                "FROM memory_records WHERE memory_id = ?",
                (memory_id,),
            )
            row = cursor.fetchone()
        except Exception as e:
            logger.error("Failed to retrieve memory record", exc_info=e)
            return None
        finally:
            self._lock.release()

        if row is None:
            return None

        try:
            return MemoryRecord(
                memory_id=row[0],
                memory_type=row[1],
                created_at=datetime.fromisoformat(row[2]),
                content=json.loads(row[3]),
                metadata=json.loads(row[4]),
                validation_status=row[5],
                operation_id=row[6],
                agent_id=row[7],
            )
        except Exception as e:
            logger.error("Failed to reconstruct memory record from row", exc_info=e)
            return None

    def delete(self, memory_id: str) -> bool:
        if self._conn is None:
            logger.error("Connection not available, cannot delete record")
            return False
        try:
            self._lock.acquire()
            cursor = self._conn.execute(
                "DELETE FROM memory_records WHERE memory_id = ?",
                (memory_id,),
            )
            self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error("Failed to delete memory record", exc_info=e)
            return False
        finally:
            self._lock.release()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as e:
                logger.error("Failed to close SQLite connection", exc_info=e)
            finally:
                self._conn = None

    def __enter__(self) -> SqliteMemoryStorage:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any | None) -> None:
        self.close()
