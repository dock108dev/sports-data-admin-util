"""Custom exceptions for social ingestion."""

from __future__ import annotations


class SocialRateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class XCircuitBreakerError(RuntimeError):
    """Raised when too many consecutive X errors trigger the circuit breaker."""

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
