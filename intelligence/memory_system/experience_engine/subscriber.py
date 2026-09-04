"""
Experience Engine Subscriber Module.

This module handles the asynchronous processing and storage of experience events
derived from strategy signals and their execution outcomes. It implements a
multi-tier memory system (episodic, procedural, semantic) with strict validation,
bounded growth, and robust error handling to ensure the signal path is never blocked.
"""

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field, field_validator

# Configure structured logging
logger = logging.getLogger("intelligence.memory_system.experience_engine")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class MemoryError(Exception):
    """Custom exception for memory system failures."""
    pass


class MemoryTier(Enum):
    """Enumeration for different memory storage tiers."""
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    SEMANTIC = "semantic"


class ExperienceStatus(Enum):
    """Status of an experience event processing."""
    SUCCESS = "success"
    SKIPPED_INVALID = "skipped_invalid"
    DROPPED_STORAGE_ERROR = "dropped_storage_error"
    DROPPED_NO_OUTCOME = "dropped_no_outcome"


@dataclass
class ForgettingPolicy:
    """
    Configuration for memory decay and forgetting.
    
    Attributes:
        decay_rate: Rate at which memory relevance decays over time.
        min_relevance: Threshold below which memories are considered forgotten.
        max_age_seconds: Maximum age for a memory before forced deletion.
    """
    decay_rate: float = 0.01
    min_relevance: float = 0.1
    max_age_seconds: float = 86400.0  # 24 hours


class StrategySignalEventV1(BaseModel):
    """
    Frozen model representing the original strategy signal.
    
    Attributes:
        signal_id: Unique identifier for the signal.
        symbol: Trading symbol associated with the signal.
        direction: Direction of the signal (buy/sell/hold).
        confidence: Confidence score of the signal (0.0 to 1.0).
        regime: Market regime at the time of signal generation.
        timestamp: Unix timestamp of signal generation.
        metadata: Additional metadata associated with the signal.
    """
    signal_id: str = Field(..., description="Unique identifier for the signal")
    symbol: str = Field(..., description="Trading symbol")
    direction: str = Field(..., description="Signal direction")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    regime: str = Field(..., description="Market regime")
    timestamp: float = Field(..., description="Unix timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        allowed = {"buy", "sell", "hold"}
        if v.lower() not in allowed:
            raise ValueError(f"Direction must be one of {allowed}")
        return v.lower()


class ExecutionOutcome(BaseModel):
    """
    Frozen model representing the execution outcome of a signal.
    
    Attributes:
        outcome_id: Unique identifier for the outcome.
        signal_id: Reference to the original signal.
        success: Whether the execution was successful.
        pnl: Profit and loss associated with the outcome.
        execution_time: Time taken for execution.
        error_message: Error message if execution failed.
    """
    outcome_id: str = Field(..., description="Unique identifier for the outcome")
    signal_id: str = Field(..., description="Reference to original signal")
    success: bool = Field(..., description="Execution success status")
    pnl: float = Field(default=0.0, description="Profit and loss")
    execution_time: float = Field(default=0.0, ge=0.0, description="Execution time in seconds")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")


class RiskAssessment(BaseModel):
    """
    Frozen model representing risk assessment for the experience.
    
    Attributes:
        risk_score: Risk score (0.0 to 1.0).
        volatility: Volatility metric at time of outcome.
        drawdown: Drawdown metric.
    """
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Risk score")
    volatility: float = Field(default=0.0, ge=0.0, description="Volatility metric")
    drawdown: float = Field(default=0.0, ge=0.0, description="Drawdown metric")


class ExperienceEvent(BaseModel):
    """
    Frozen model representing a complete experience event.
    
    Attributes:
        event_id: Unique identifier for the experience event.
        signal: The original strategy signal.
        outcome: The execution outcome.
        risk_assessment: Risk assessment data.
        timestamp: Unix timestamp of experience creation.
    """
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique event ID")
    signal: StrategySignalEventV1 = Field(..., description="Original strategy signal")
    outcome: ExecutionOutcome = Field(..., description="Execution outcome")
    risk_assessment: RiskAssessment = Field(..., description="Risk assessment")
    timestamp: float = Field(default_factory=time.time, description="Experience timestamp")

    @field_validator("outcome")
    @classmethod
    def validate_outcome_link(cls, v: ExecutionOutcome, values: Dict[str, Any]) -> ExecutionOutcome:
        signal = values.get("signal")
        if signal and v.signal_id != signal.signal_id:
            raise ValueError("Outcome signal_id must match signal signal_id")
        return v


class MemoryRecord(BaseModel):
    """
    Internal representation of a stored memory record.
    
    Attributes:
        record_id: Unique identifier for the memory record.
        tier: Memory tier (episodic, procedural, semantic).
        data: The actual memory data.
        relevance: Current relevance score.
        created_at: Creation timestamp.
        last_accessed: Last access timestamp.
        access_count: Number of times accessed.
    """
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique record ID")
    tier: MemoryTier = Field(..., description="Memory tier")
    data: Dict[str, Any] = Field(..., description="Memory data")
    relevance: float = Field(default=1.0, ge=0.0, le=1.0, description="Relevance score")
    created_at: float = Field(default_factory=time.time, description="Creation timestamp")
    last_accessed: float = Field(default_factory=time.time, description="Last access timestamp")
    access_count: int = Field(default=0, ge=0, description="Access count")


class ExperienceSubscriber:
    """
    Asynchronous subscriber for processing and storing experience events.
    
    This class handles the validation, routing, and storage of experience events
    into episodic, procedural, and semantic memory stores. It implements bounded
    memory growth, forgetting policies, and robust error handling to ensure
    the signal path is never blocked.
    
    Attributes:
        max_episodic_size: Maximum number of episodic memory records.
        max_procedural_size: Maximum number of procedural memory records.
        max_semantic_size: Maximum number of semantic memory records.
        forgetting_policy: Configuration for memory decay.
        storage_retry_count: Number of retries for storage operations.
        storage_retry_delay: Delay between storage retries in seconds.
    """
    
    def __init__(
        self,
        max_episodic_size: int = 10000,
        max_procedural_size: int = 1000,
        max_semantic_size: int = 5000,
        forgetting_policy: Optional[ForgettingPolicy] = None,
        storage_retry_count: int = 3,
        storage_retry_delay: float = 0.1
    ) -> None:
        """
        Initialize the ExperienceSubscriber.
        
        Args:
            max_episodic_size: Maximum number of episodic memory records.
            max_procedural_size: Maximum number of procedural memory records.
            max_semantic_size: Maximum number of semantic memory records.
            forgetting_policy: Configuration for memory decay.
            storage_retry_count: Number of retries for storage operations.
            storage_retry_delay: Delay between storage retries in seconds.
        """
        self._max_episodic_size = max_episodic_size
        self._max_procedural_size = max_procedural_size
        self._max_semantic_size = max_semantic_size
        self._forgetting_policy = forgetting_policy or ForgettingPolicy()
        self._storage
    @staticmethod
    def _detect_event_type(payload: dict) -> str:
        """Detect event type from payload keys.
        
        Used by tests and routing logic to classify incoming events.
        """
        if "order_id" in payload:
            return "execution_outcome"
        if "assessment_type" in payload:
            return "risk_assessment"
        if "decision_type" in payload:
            return "agent_decision"
        return "unknown"
