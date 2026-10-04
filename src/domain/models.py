"""Immutable domain models for the service-desk business boundary."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
]
IdempotencyKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=8, max_length=255),
]
NonBlankText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


def _require_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"unknown IANA timezone: {value}") from error
    return value


class DomainModel(BaseModel):
    """Base configuration shared by immutable domain values."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class PreferredLanguage(StrEnum):
    ENGLISH = "en"
    HINDI = "hi"
    HINGLISH = "hinglish"


class AppointmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class WriteDisposition(StrEnum):
    CREATED = "created"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    ALREADY_CANCELLED = "already_cancelled"


class Customer(DomainModel):
    customer_id: Identifier
    full_name: NonBlankText
    phone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=7, max_length=32)]
    preferred_language: PreferredLanguage


class Vehicle(DomainModel):
    vehicle_id: Identifier
    customer_id: Identifier
    registration_number: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=4, max_length=32),
    ]
    make: NonBlankText
    model: NonBlankText
    year: int = Field(ge=1886, le=2100)


class OpeningHours(DomainModel):
    """Local branch opening interval for a Python weekday (Monday is zero)."""

    weekday: int = Field(ge=0, le=6)
    opens_at: time
    closes_at: time

    @field_validator("opens_at", "closes_at")
    @classmethod
    def require_local_wall_time(cls, value: time) -> time:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("opening hours must use timezone-naive local wall times")
        return value

    @model_validator(mode="after")
    def require_positive_interval(self) -> Self:
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be later than opens_at")
        return self


class Branch(DomainModel):
    branch_id: Identifier
    name: NonBlankText
    locality: NonBlankText
    city: NonBlankText
    timezone: str = "Asia/Kolkata"
    opening_hours: tuple[OpeningHours, ...] = ()
    supported_service_ids: tuple[Identifier, ...] = ()

    @field_validator("timezone")
    @classmethod
    def require_known_timezone(cls, value: str) -> str:
        return _validate_timezone(value)

    @model_validator(mode="after")
    def require_unique_configuration(self) -> Self:
        weekdays = [hours.weekday for hours in self.opening_hours]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError("opening_hours must contain at most one interval per weekday")
        if len(self.supported_service_ids) != len(set(self.supported_service_ids)):
            raise ValueError("supported_service_ids must be unique")
        return self


class ServiceType(DomainModel):
    service_id: Identifier
    name: NonBlankText
    duration_minutes: int = Field(gt=0, le=24 * 60)
    description: NonBlankText
    base_price: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)


class Appointment(DomainModel):
    appointment_id: Identifier
    customer_id: Identifier
    vehicle_id: Identifier
    branch_id: Identifier
    service_id: Identifier
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    idempotency_key: IdempotencyKey
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("start_at", "end_at", "created_at", "updated_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "datetime")
        return _require_aware(value, field_name)

    @model_validator(mode="after")
    def require_consistent_timeline(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be later than start_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self


class AppointmentInterval(DomainModel):
    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "datetime")
        return _require_aware(value, field_name)

    @model_validator(mode="after")
    def require_positive_interval(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be later than start_at")
        return self


class AvailableSlot(AppointmentInterval):
    pass


class Availability(DomainModel):
    branch_id: Identifier
    service_id: Identifier
    on_date: date
    timezone: str
    slots: tuple[AvailableSlot, ...]

    @field_validator("timezone")
    @classmethod
    def require_known_timezone(cls, value: str) -> str:
        return _validate_timezone(value)


class ConfirmedWriteCommand(DomainModel):
    confirmed: bool
    idempotency_key: IdempotencyKey


class CreateAppointmentCommand(ConfirmedWriteCommand):
    customer_id: Identifier
    vehicle_id: Identifier
    branch_id: Identifier
    service_id: Identifier
    start_at: datetime

    @field_validator("start_at")
    @classmethod
    def require_aware_start(cls, value: datetime) -> datetime:
        return _require_aware(value, "start_at")


class RescheduleAppointmentCommand(ConfirmedWriteCommand):
    appointment_id: Identifier
    new_start_at: datetime
    expected_version: int = Field(ge=1)

    @field_validator("new_start_at")
    @classmethod
    def require_aware_start(cls, value: datetime) -> datetime:
        return _require_aware(value, "new_start_at")


class CancelAppointmentCommand(ConfirmedWriteCommand):
    appointment_id: Identifier
    expected_version: int = Field(ge=1)


class AppointmentWriteOutcome(DomainModel):
    disposition: WriteDisposition
    appointment: Appointment
    request_fingerprint: Annotated[
        str,
        StringConstraints(pattern=r"^[0-9a-f]{64}$"),
    ]
