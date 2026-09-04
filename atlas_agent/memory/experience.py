"""Experience data model for generator learning memory."""

__all__ = ['Experience', 'Source', 'Method', 'Artifact', 'Decision']


import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum


class Decision(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


@dataclass(frozen=True)
class Source:
    provider: str
    model: str
    prompt_hash: str


@dataclass(frozen=True)
class Method:
    context_sources: list[str]
    temperature: float


@dataclass(frozen=True)
class Artifact:
    language: str
    module: str
    governance_refs: list[str]


@dataclass(frozen=True)
class Outcome:
    human_decision: str
    reason: str
    quality_score: float


@dataclass
class Experience:
    id: str
    ts: str
    type: str
    source: Source
    method: Method
    artifact: Artifact
    outcome: Outcome
    anti_patterns: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_jsonl(cls, line: str) -> "Experience":
        data = json.loads(line)
        return cls(
            id=data["id"], ts=data["ts"], type=data["type"],
            source=Source(**data["source"]),
            method=Method(**data["method"]),
            artifact=Artifact(**data["artifact"]),
            outcome=Outcome(**data["outcome"]),
            anti_patterns=data.get("anti_patterns", []),
            tags=data.get("tags", []),
        )

    @staticmethod
    def generate_id() -> str:
        raw = f"{time.time()}-{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:8]}"
        return f"mem_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"