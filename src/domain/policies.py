"""Pure validation, scheduling, and request-fingerprinting policies."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import cast
from zoneinfo import ZoneInfo

from pydantic import BaseModel, TypeAdapter, ValidationError

from .errors import ConfirmationRequiredError, DomainError, ErrorCode
from .models import (
    AppointmentInterval,
    AvailableSlot,
    Branch,
    ConfirmedWriteCommand,
    Identifier,
    ServiceType,
    Vehicle,
)

_IDENTIFIER_ADAPTER: TypeAdapter[str] = TypeAdapter(Identifier)
_PHONE_SEPARATORS = re.compile(r"[\s().-]+")
_WRITE_CONTROL_FIELDS = {"confirmed", "idempotency_key"}


def validate_identifier(value: str, *, field_name: str) -> str:
    """Validate an identifier supplied outside a Pydantic command model."""

    try:
        return _IDENTIFIER_ADAPTER.validate_python(value)
    except ValidationError as error:
        raise DomainError(
            ErrorCode.INVALID_IDENTIFIER,
            f"{field_name} is invalid",
            details={"field": field_name},
        ) from error


def normalize_phone(value: str) -> str:
    """Normalize common phone formatting without guessing a country code."""

    normalized = _PHONE_SEPARATORS.sub("", value.strip())
    prefix = "+" if normalized.startswith("+") else ""
    digits = normalized[1:] if prefix else normalized
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        raise DomainError(
            ErrorCode.INVALID_PHONE,
            "phone must contain 7 to 15 digits and may start with '+'",
        )
    return f"{prefix}{digits}"


def normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise DomainError(
            ErrorCode.INVALID_IDENTIFIER,
            f"{field_name} cannot be blank",
            details={"field": field_name},
        )
    return normalized


def require_confirmed(command: ConfirmedWriteCommand) -> None:
    if not command.confirmed:
        raise ConfirmationRequiredError()


def require_aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainError(
            ErrorCode.NAIVE_DATETIME,
            f"{field_name} must be timezone-aware",
            details={"field": field_name},
        )
    return value


def require_future(value: datetime, *, now: datetime, field_name: str) -> None:
    require_aware(value, field_name=field_name)
    require_aware(now, field_name="now")
    if value <= now:
        raise DomainError(
            ErrorCode.START_TIME_NOT_FUTURE,
            f"{field_name} must be later than the current time",
            details={"field": field_name},
        )


def require_current_or_future_date(
    value: date,
    *,
    branch: Branch,
    now: datetime,
) -> None:
    require_aware(now, field_name="now")
    local_today = now.astimezone(ZoneInfo(branch.timezone)).date()
    if value < local_today:
        raise DomainError(
            ErrorCode.INVALID_DATE,
            "availability date cannot be in the past",
            details={"branch_id": branch.branch_id},
        )


def require_supported_service(branch: Branch, service_id: str) -> None:
    if service_id not in branch.supported_service_ids:
        raise DomainError(
            ErrorCode.UNSUPPORTED_SERVICE,
            "branch does not support the requested service",
            details={"branch_id": branch.branch_id, "service_id": service_id},
        )


def require_vehicle_owner(vehicle: Vehicle, customer_id: str) -> None:
    if vehicle.customer_id != customer_id:
        raise DomainError(
            ErrorCode.VEHICLE_CUSTOMER_MISMATCH,
            "vehicle does not belong to the requested customer",
            details={
                "vehicle_id": vehicle.vehicle_id,
                "customer_id": customer_id,
            },
        )


def require_within_opening_hours(
    *,
    branch: Branch,
    service: ServiceType,
    start_at: datetime,
) -> None:
    """Require an appointment interval to fit one branch opening interval."""

    require_aware(start_at, field_name="start_at")
    local_start = start_at.astimezone(ZoneInfo(branch.timezone))
    local_end = local_start + timedelta(minutes=service.duration_minutes)
    hours = _opening_hours_for(branch, local_start.weekday())
    if hours is None:
        _raise_outside_opening_hours(branch, service, local_start)

    assert hours is not None
    opening = datetime.combine(local_start.date(), hours.opens_at, local_start.tzinfo)
    closing = datetime.combine(local_start.date(), hours.closes_at, local_start.tzinfo)
    if local_start < opening or local_end > closing:
        _raise_outside_opening_hours(branch, service, local_start)


def require_slot_cadence(
    *,
    branch: Branch,
    start_at: datetime,
    slot_interval_minutes: int,
) -> None:
    """Require a local start time to align with the configured daily cadence."""

    if slot_interval_minutes <= 0:
        raise ValueError("slot_interval_minutes must be positive")
    require_aware(start_at, field_name="start_at")
    local_start = start_at.astimezone(ZoneInfo(branch.timezone))
    minutes_from_midnight = local_start.hour * 60 + local_start.minute
    if (
        local_start.second != 0
        or local_start.microsecond != 0
        or minutes_from_midnight % slot_interval_minutes != 0
    ):
        raise DomainError(
            ErrorCode.INVALID_SLOT_CADENCE,
            "appointment start must align with the branch slot cadence",
            details={
                "branch_id": branch.branch_id,
                "local_start": local_start.isoformat(),
                "slot_interval_minutes": slot_interval_minutes,
            },
        )


def availability_window(branch: Branch, on_date: date) -> tuple[datetime, datetime]:
    """Return the branch-local day as a timezone-aware half-open interval."""

    timezone = ZoneInfo(branch.timezone)
    start = datetime.combine(on_date, time.min, timezone)
    end = datetime.combine(on_date + timedelta(days=1), time.min, timezone)
    return start, end


def generate_available_slots(
    *,
    branch: Branch,
    service: ServiceType,
    on_date: date,
    busy_intervals: Sequence[AppointmentInterval],
    now: datetime,
    slot_interval_minutes: int = 30,
) -> tuple[AvailableSlot, ...]:
    """Generate deterministic half-open slots from hours and busy intervals."""

    if slot_interval_minutes <= 0:
        raise ValueError("slot_interval_minutes must be positive")
    require_aware(now, field_name="now")
    require_current_or_future_date(on_date, branch=branch, now=now)
    require_supported_service(branch, service.service_id)

    hours = _opening_hours_for(branch, on_date.weekday())
    if hours is None:
        return ()

    timezone = ZoneInfo(branch.timezone)
    opening = datetime.combine(on_date, hours.opens_at, timezone)
    closing = datetime.combine(on_date, hours.closes_at, timezone)
    duration = timedelta(minutes=service.duration_minutes)
    interval = timedelta(minutes=slot_interval_minutes)
    now_utc = now.astimezone(UTC)

    slots: list[AvailableSlot] = []
    candidate = opening
    while candidate + duration <= closing:
        candidate_end = candidate + duration
        if candidate.astimezone(UTC) > now_utc and not any(
            _overlaps(candidate, candidate_end, busy) for busy in busy_intervals
        ):
            slots.append(AvailableSlot(start_at=candidate, end_at=candidate_end))
        candidate += interval
    return tuple(slots)


def command_fingerprint(operation: str, command: ConfirmedWriteCommand) -> str:
    """Hash a write's semantic payload, excluding authorization/retry controls."""

    operation_name = operation.strip()
    if not operation_name:
        raise ValueError("operation cannot be blank")
    payload = command.model_dump(mode="python", exclude=_WRITE_CONTROL_FIELDS)
    return canonical_request_fingerprint(operation_name, payload)


def canonical_request_fingerprint(operation: str, payload: Mapping[str, object]) -> str:
    """Return SHA-256 over canonical JSON for a normalized request payload."""

    envelope = {"operation": operation, "payload": _canonicalize(payload)}
    encoded = json.dumps(
        envelope,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonicalize(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python"))
    if isinstance(value, datetime):
        require_aware(value, field_name="fingerprint datetime")
        utc_value = value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return _canonicalize(value.value)
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(mapping.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast(Sequence[object], value)
        return [_canonicalize(item) for item in sequence]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported fingerprint value: {type(value).__name__}")


def _opening_hours_for(branch: Branch, weekday: int):
    return next(
        (hours for hours in branch.opening_hours if hours.weekday == weekday),
        None,
    )


def _overlaps(
    candidate_start: datetime,
    candidate_end: datetime,
    busy: AppointmentInterval,
) -> bool:
    return candidate_start < busy.end_at and candidate_end > busy.start_at


def _raise_outside_opening_hours(
    branch: Branch,
    service: ServiceType,
    local_start: datetime,
) -> None:
    raise DomainError(
        ErrorCode.OUTSIDE_OPENING_HOURS,
        "appointment does not fit within branch opening hours",
        details={
            "branch_id": branch.branch_id,
            "service_id": service.service_id,
            "local_start": local_start.isoformat(),
        },
    )
