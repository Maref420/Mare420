# MODULE: atlas-customer-agent
# GOVERNANCE: Matrix C - Python Intelligence Layer
# WARNING: Atomic writes. Thread-safe. No bare except.
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from typing import Any

from .models import AppError, CustomerRecord

logger = logging.getLogger(__name__)


class CustomerStore:
    def __init__(self, path: str = "./data/customers.json") -> None:
        self.path = path
        self._lock = threading.Lock()
        self._records: list[CustomerRecord] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            dir_name = os.path.dirname(self.path) or "."
            os.makedirs(dir_name, exist_ok=True)
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self._records = [CustomerRecord.model_validate(r) for r in data]
            logger.info("store_loaded", extra={"count": len(self._records)})
        except json.JSONDecodeError as e:
            raise AppError("INT_STORE_CORRUPT", "Invalid JSON in store", retryable=False) from e
        except OSError as e:
            raise AppError("INT_STORE_IO", "Cannot read store file", retryable=False) from e
        except ValueError as e:
            raise AppError("VAL_STORE_SCHEMA", "Schema validation failed", retryable=False) from e

    def _save(self, records: list[CustomerRecord]) -> None:
        dir_name = os.path.dirname(self.path) or "."
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=dir_name, suffix=".tmp", delete=False) as tmp:
                data = [r.model_dump() for r in records]
                json.dump(data, tmp, indent=2, default=str)
                tmp_path = tmp.name
            os.replace(tmp_path, self.path)
        except OSError as e:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise AppError("INT_STORE_WRITE", "Failed to persist store", retryable=False) from e

    def get(self, customer_id: str) -> CustomerRecord | None:
        for r in self._records:
            if r.customer_id == customer_id:
                return r
        return None

    def exists(self, customer_id: str) -> bool:
        return self.get(customer_id) is not None

    def add(self, record: CustomerRecord) -> None:
        with self._lock:
            if self.exists(record.customer_id):
                raise AppError("VAL_DUPLICATE_CUSTOMER", f"Customer '{record.customer_id}' already exists", retryable=False)
            self._records.append(record)
            self._save(self._records)

    def update(self, customer_id: str, updates: dict[str, Any]) -> CustomerRecord:
        with self._lock:
            for i, r in enumerate(self._records):
                if r.customer_id == customer_id:
                    updated = {**r.model_dump(), **updates}
                    self._records[i] = CustomerRecord.model_validate(updated)
                    self._save(self._records)
                    return self._records[i]
            raise AppError("VAL_CUSTOMER_NOT_FOUND", f"Customer '{customer_id}' not found", retryable=False)

    def delete(self, customer_id: str) -> None:
        with self._lock:
            for i, r in enumerate(self._records):
                if r.customer_id == customer_id:
                    updated = {**r.model_dump(), "status": "deleted"}
                    self._records[i] = CustomerRecord.model_validate(updated)
                    self._save(self._records)
                    return
            raise AppError("VAL_CUSTOMER_NOT_FOUND", f"Customer '{customer_id}' not found", retryable=False)

    def list_active(self) -> list[CustomerRecord]:
        with self._lock:
            return [r for r in self._records if r.status == "active"]
