"""
ATLAS-AI POLYGLOT SYSTEM
DOMAIN: self_correcting_loop
PURPOSE: Self-correcting loop with portable memory for code repair
         against governance rules and project contracts.
STATUS: ⚠️ OG-GENERATED — REVIEW REQUIRED
"""
from .loop import AttemptRecord, QualityScore, RepairStrategy, SelfCorrectingLoop
from .portable_memory import AntiPatternRecord, KnowledgeEntry, MemoryExperience, PortableMemory, StrategyStats
from .pattern_extractor import ErrorCategory, ExtractedPattern, PatternExtractor
from .learning_memory import LearningMemory
from .experience import Artifact, Decision, Experience, Method, Outcome, Source

__all__ = [
    "AttemptRecord", "QualityScore", "RepairStrategy", "SelfCorrectingLoop",
    "AntiPatternRecord", "KnowledgeEntry", "MemoryExperience", "PortableMemory", "StrategyStats",
    "ErrorCategory", "ExtractedPattern", "PatternExtractor",
    "LearningMemory",
    "Artifact", "Decision", "Experience", "Method", "Outcome", "Source",
]
