"""
Atlas AI Foundation Metrics Module.

Governance Reference: CONSTITUTION.md v1.2, Section 8 (Python Engine Rules).
Ownership: Intelligence layer (Python).
Module: python_metrics
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class _Labels:
    """Frozen dataclass for internal label storage."""
    key: str = ""
    value: str = ""


class Counter:
    """
    A counter metric.
    
    Attributes:
        name: Name of the metric.
        help: Help text for the metric.
    """
    def __init__(self, name: str, help: str) -> None:
        self.name: str = name
        self._help: str = help
        self._value: float = 0.0
        self._lock: threading.Lock = threading.Lock()

    def increment(self, amount: float = 1.0) -> None:
        """Increment the counter by the given amount."""
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        """Return the current value of the counter."""
        with self._lock:
            return self._value


class Gauge:
    """
    A gauge metric.
    
    Attributes:
        name: Name of the metric.
        help: Help text for the metric.
    """
    def __init__(self, name: str, help: str) -> None:
        self.name: str = name
        self._help: str = help
        self._value: float = 0.0
        self._lock: threading.Lock = threading.Lock()

    def set(self, value: float) -> None:
        """Set the gauge to the given value."""
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        """Increment the gauge by the given amount."""
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        """Decrement the gauge by the given amount."""
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        """Return the current value of the gauge."""
        with self._lock:
            return self._value


class Histogram:
    """
    A histogram metric.
    
    Attributes:
        name: Name of the metric.
        help: Help text for the metric.
        buckets: Tuple of bucket boundaries.
    """
    DEFAULT_BUCKETS: Tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self, 
        name: str, 
        help: str, 
        buckets: Optional[Tuple[float, ...]] = None
    ) -> None:
        self.name: str = name
        self._help: str = help
        self._buckets: Tuple[float, ...] = buckets or self.DEFAULT_BUCKETS
        self._count: int = 0
        self._sum: float = 0.0
        self._bucket_counts: Dict[float, int] = {b: 0 for b in self._buckets}
        self._lock: threading.Lock = threading.Lock()

    def observe(self, value: float) -> None:
        """Observe the given value."""
        with self._lock:
            self._count += 1
            self._sum += value
            for b in self._buckets:
                if value <= b:
                    self._bucket_counts[b] += 1

    @property
    def count(self) -> int:
        """Return the total number of observations."""
        with self._lock:
            return self._count

    @property
    def sum(self) -> float:
        """Return the sum of all observed values."""
        with self._lock:
            return self._sum

    @property
    def buckets(self) -> Dict[float, int]:
        """Return the bucket counts."""
        with self._lock:
            return dict(self._bucket_counts)


class MetricsRegistry:
    """
    Registry for managing metrics.
    
    Attributes:
        metrics: Dictionary mapping metric names to metric instances.
    """
    def __init__(self) -> None:
        self.metrics: Dict[str, Any] = {}
        self._lock: threading.Lock = threading.Lock()

    def register(self, metric: Any) -> None:
        """Register a metric with the registry."""
        with self._lock:
            self.metrics[metric.name] = metric

    def get(self, name: str) -> Any:
        """Retrieve a metric by name."""
        with self._lock:
            return self.metrics.get(name)

    def export_prometheus(self) -> str:
        """
        Export all metrics in Prometheus text exposition format.
        
        Returns:
            Formatted Prometheus text string.
        """
        output_lines: List[str] = []
        with self._lock:
            for metric in self.metrics.values():
                # Header
                output_lines.append(f"# HELP {metric.name} {metric._help}")
                output_lines.append(f"# TYPE {metric.name} {type(metric).__name__.lower()}")
                
                if isinstance(metric, Counter):
                    output_lines.append(f"{metric.name} {metric.value:.6f}")
                elif isinstance(metric, Gauge):
                    output_lines.append(f"{metric.name} {metric.value:.6f}")
                elif isinstance(metric, Histogram):
                    # Histogram requires special handling for count, sum, and buckets
                    output_lines.append(f"{metric.name}_count {metric.count}")
                    output_lines.append(f"{metric.name}_sum {metric.sum:.6f}")
                    for b in metric._buckets:
                        # +Inf bucket is implied by count, but standard exposition often includes it if explicit
                        output_lines.append(f'{metric.name}_bucket{{le="{b}"}} {metric._bucket_counts[b]}')
                    # Usually +Inf is required by Prometheus
                    output_lines.append(f'{metric.name}_bucket{{le="+Inf"}} {metric.count}')
                
                output_lines.append("") # Newline between metrics

        return "\n".join(output_lines)
