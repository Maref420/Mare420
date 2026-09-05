"""Foundation error envelope — governance-compliant cross-service errors."""
from .python_error import (
    ErrorEnvelope,
    AppError,
    val_error,
    auth_error,
    biz_error,
    dep_error,
    res_error,
    net_error,
    int_error,
    should_retry,
)

__all__ = [
    "ErrorEnvelope",
    "AppError",
    "val_error",
    "auth_error",
    "biz_error",
    "dep_error",
    "res_error",
    "net_error",
    "int_error",
    "should_retry",
]
