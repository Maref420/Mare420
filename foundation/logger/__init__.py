"""Foundation structured logger — governance-compliant observability."""
from .python_logger import (
    setup_logger,
    get_trace_id,
    set_trace_id,
    new_span,
    timed,
)

__all__ = ["setup_logger", "get_trace_id", "set_trace_id", "new_span", "timed"]
