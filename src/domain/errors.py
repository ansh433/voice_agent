"""Stable domain errors exposed across storage and agent boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class ErrorCode(StrEnum):
    INVALID_IDENTIFIER = "invalid_identifier"
    INVALID_PHONE = "invalid_phone"
    INVALID_DATE = "invalid_date"
    NAIVE_DATETIME = "naive_datetime"
    START_TIME_NOT_FUTURE = "start_time_not_future"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CUSTOMER_NOT_FOUND = "customer_not_found"
    VEHICLE_NOT_FOUND = "vehicle_not_found"
    VEHICLE_CUSTOMER_MISMATCH = "vehicle_customer_mismatch"
    BRANCH_NOT_FOUND = "branch_not_found"
    SERVICE_NOT_FOUND = "service_not_found"
    UNSUPPORTED_SERVICE = "unsupported_service"
    APPOINTMENT_NOT_FOUND = "appointment_not_found"
    OUTSIDE_OPENING_HOURS = "outside_opening_hours"
    INVALID_SLOT_CADENCE = "invalid_slot_cadence"
    SLOT_CONFLICT = "slot_conflict"
    IDEMPOTENCY_KEY_REUSED = "idempotency_key_reused"
    VERSION_CONFLICT = "version_conflict"
    INVALID_APPOINTMENT_STATE = "invalid_appointment_state"
    STORAGE_UNAVAILABLE = "storage_unavailable"


class DomainError(Exception):
    """Expected business failure with a stable machine-readable code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = MappingProxyType(dict(details or {}))

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.code!r}, message={self.message!r}, "
            f"details={dict(self.details)!r})"
        )


class ConfirmationRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.CONFIRMATION_REQUIRED,
            "explicit caller confirmation is required",
        )


class EntityNotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class StorageUnavailableError(DomainError):
    """Storage adapter failure safe to expose across the domain boundary."""

    def __init__(
        self,
        message: str = "business storage is temporarily unavailable",
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(ErrorCode.STORAGE_UNAVAILABLE, message, details=details)
