"""Storage-facing protocol for the business domain."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from .models import (
    Appointment,
    AppointmentInterval,
    AppointmentWriteOutcome,
    Branch,
    CancelAppointmentCommand,
    CreateAppointmentCommand,
    Customer,
    RescheduleAppointmentCommand,
    ServiceType,
    Vehicle,
)


class BusinessRepository(Protocol):
    """Async persistence contract implemented atomically by the storage layer."""

    async def lookup_customer_by_phone(self, phone: str) -> Customer | None: ...

    async def list_branches(self, city: str | None = None) -> Sequence[Branch]: ...

    async def list_services(self, branch_id: str | None = None) -> Sequence[ServiceType]: ...

    async def get_customer(self, customer_id: str) -> Customer | None: ...

    async def get_vehicle(self, vehicle_id: str) -> Vehicle | None: ...

    async def get_branch(self, branch_id: str) -> Branch | None: ...

    async def get_service(self, service_id: str) -> ServiceType | None: ...

    async def get_appointment(self, appointment_id: str) -> Appointment | None: ...

    async def list_active_appointment_intervals(
        self,
        branch_id: str,
        service_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Sequence[AppointmentInterval]: ...

    async def create_appointment(
        self,
        command: CreateAppointmentCommand,
        request_fingerprint: str,
    ) -> AppointmentWriteOutcome: ...

    async def reschedule_appointment(
        self,
        command: RescheduleAppointmentCommand,
        request_fingerprint: str,
    ) -> AppointmentWriteOutcome: ...

    async def cancel_appointment(
        self,
        command: CancelAppointmentCommand,
        request_fingerprint: str,
    ) -> AppointmentWriteOutcome: ...
