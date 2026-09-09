"""
ATLAS-AI POLYGLOT SYSTEM
DOMAIN: memory
LANGUAGE: Python
CONTRACT: Uses atlas_agent.LLMClient (NOT raw httpx)
RULES: R03 (source badge), R06 (governed memory), §17 (guard)
OG PROTOCOL: All enrichment via LLMClient (cached + guarded + circuit-breaker)
STATUS: ⚠️ OG-GENERATED — REVIEW REQUIRED BEFORE PRODUCTION USE
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ✅ REUSE EXISTING INFRASTRUCTURE — never duplicate
from atlas_agent.llm_client import LLMClient

logger = logging.getLogger(__name__)
MEMORY_STORE_PATH = Path("data/memory_store.json")


@dataclass(frozen=True)
class GovernedMemoryRecord:
    """Immutable memory record with full provenance (R06)."""
    id: str
    content: str
    title: Optional[str]
    memory_type: str          # fact|decision|preference|warning
    weight: float             # 0.0–1.0, set by OG enrichment
    source_uri: str           # R03: MANDATORY provenance
    agent_id: str             # R06: who wrote this
    enrichment_complete: bool
    created_at: float


class GovernedMemoryStore:
    """
    Governed memory store using existing LLMClient for enrichment.

    Security layers (automatic via LLMClient):
      Layer 1: RestrictionGuard (§17) blocks forbidden content BEFORE sending
      Layer 4: LLMCache prevents redundant OG calls
      Layer 5: Key auto-redacted in all logs (llm_client.py:157-158)

    ⚠️ OG-GENERATED — REVIEW REQUIRED
    """

    ENRICHMENT_PROMPT_TEMPLATE = (
        'Analyze this memory and return ONLY valid JSON:\n'
        'Content: "{content}"\n'
        'Return exactly: {{"title": "<concise title>", '
        '"memory_type": "<fact|decision|preference|warning>", '
        '"weight": <0.0 to 1.0>}}'
    )

    def __init__(self) -> None:
        self._llm = LLMClient()
        MEMORY_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        logger.info("GovernedMemoryStore initialized")

    def _load(self) -> list[dict]:
        if MEMORY_STORE_PATH.exists():
            return json.loads(MEMORY_STORE_PATH.read_text(encoding="utf-8"))
        return []

    def _save(self, records: list[dict]) -> None:
        MEMORY_STORE_PATH.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    async def write(
        self,
        agent_id: str,
        content: str,
        source_uri: str,
    ) -> GovernedMemoryRecord:
        if not source_uri:
            raise ValueError(
                "VAL_MISSING_SOURCE_BADGE: source_uri is mandatory per R03"
            )

        record_id = str(uuid.uuid4())[:8]
        created_at = time.time()

        record = GovernedMemoryRecord(
            id=record_id, content=content, title=None,
            memory_type="fact", weight=0.5, source_uri=source_uri,
            agent_id=agent_id, enrichment_complete=False, created_at=created_at,
        )
        records = self._load()
        records.append(asdict(record))
        self._save(records)
        logger.info("Memory %s written (pending enrichment)", record_id)

        try:
            prompt = self.ENRICHMENT_PROMPT_TEMPLATE.format(content=content)
            response = await self._llm.complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100, temperature=0.1,
            )
            text = response.strip() if isinstance(response, str) else str(response)
            start = text.find("{")
            end = text.rfind("}") + 1
            if start < 0 or end <= start:
                raise ValueError(f"Invalid JSON in OG response: {text[:100]}")

            enriched = json.loads(text[start:end])
            record = GovernedMemoryRecord(
                id=record_id, content=content,
                title=str(enriched.get("title", "")) or None,
                memory_type=str(enriched.get("memory_type", "fact")),
                weight=float(enriched.get("weight", 0.5)),
                source_uri=source_uri, agent_id=agent_id,
                enrichment_complete=True, created_at=created_at,
            )
            records = [r for r in records if r["id"] != record_id]
            records.append(asdict(record))
            self._save(records)
            logger.info(
                "Memory %s enriched: type=%s weight=%.2f title=%s",
                record_id, record.memory_type, record.weight, record.title,
            )
        except Exception as e:
            logger.warning("Enrichment failed for %s: %s", record_id, e)

        return record

    def recall(self, query: str, limit: int = 5) -> list[GovernedMemoryRecord]:
        records = self._load()
        q = query.lower()
        scored: list[tuple[float, dict]] = []
        for r in records:
            score = 0.0
            if q in r.get("content", "").lower():
                score += r.get("weight", 0.5)
            if r.get("title") and q in r["title"].lower():
                score += 0.3
            if score > 0:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [GovernedMemoryRecord(**r) for _, r in scored[:limit]]
