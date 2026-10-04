"""Business-service interface and repository-backed implementation."""

from __future__ import annotations

from datetime import date
from typing import Never, Protocol, runtime_checkable

from .clock import Clock, SystemClock
from .errors import DomainError, EntityNotFoundError, ErrorCode
from .models import (
    Appointment,
    AppointmentWriteOutcome,
    Availability,
    Branch,
    CancelAppointmentCommand,
    CreateAppointmentCommand,
    Customer,
    RescheduleAppointmentCommand,
    ServiceType,
)
from .policies import (
    availability_window,
    command_fingerprint,
    generate_available_slots,
    normalize_optional_text,
    normalize_phone,
    require_confirmed,
    require_future,
    require_slot_cadence,
    require_supported_service,
    require_vehicle_owner,
    require_within_opening_hours,
    validate_identifier,
)
from .repositories import BusinessRepository


@runtime_checkable
class BusinessService(Protocol):
    async def lookup_customer(self, phone: str) -> Customer: ...

    async def list_branches(self, city: str | None = None) -> tuple[Branch, ...]: ...

    async def list_services(
        self,
        branch_id: str | None = None,
    ) -> tuple[ServiceType, ...]: ...

    async def check_available_slots(
        self,
        branch_id: str,
        service_id: str,
        on_date: date,
    ) -> Availability: ...

    async def get_appointment(self, appointment_id: str) -> Appointment: ...

    async def create_appointment(
        self,
        command: CreateAppointmentCommand,
    ) -> AppointmentWriteOutcome: ...

    async def reschedule_appointment(
        self,
        command: RescheduleAppointmentCommand,
    ) -> AppointmentWriteOutcome: ...

    async def cancel_appointment(
        self,
        command: CancelAppointmentCommand,
    ) -> AppointmentWriteOutcome: ...


class DefaultBusinessService:
    """Validate business invariants and delegate atomic writes to a repository."""

    def __init__(
        self,
        repository: BusinessRepository,
        *,
        clock: Clock | None = None,
        slot_interval_minutes: int = 30,
    ) -> None:
        if slot_interval_minutes <= 0:
            raise ValueError("slot_interval_minutes must be positive")
        self._repository = repository
        self._clock = clock or SystemClock()
        self._slot_interval_minutes = slot_interval_minutes

    async def lookup_customer(self, phone: str) -> Customer:
        normalized_phone = normalize_phone(phone)
        customer = await self._repository.lookup_customer_by_phone(normalized_phone)
        if customer is None:
            _raise_not_found(
                ErrorCode.CUSTOMER_NOT_FOUND,
                entity="customer",
                lookup="phone",
            )
        return customer

    async def list_branches(self, city: str | None = None) -> tuple[Branch, ...]:
        normalized_city = normalize_optional_text(city, field_name="city")
        return tuple(await self._repository.list_branches(normalized_city))

    async def list_services(
        self,
        branch_id: str | None = None,
    ) -> tuple[ServiceType, ...]:
        if branch_id is None:
            return tuple(await self._repository.list_services())

        normalized_branch_id = validate_identifier(branch_id, field_name="branch_id")
        await self._require_branch(normalized_branch_id)
        return tuple(await self._repository.list_services(normalized_branch_id))

    async def check_available_slots(
        self,
        branch_id: str,
        service_id: str,
        on_date: date,
    ) -> Availability:
        normalized_branch_id = validate_identifier(branch_id, field_name="branch_id")
        normalized_service_id = validate_identifier(service_id, field_name="service_id")
        branch = await self._require_branch(normalized_branch_id)
        service = await self._require_service(normalized_service_id)
        require_supported_service(branch, service.service_id)

        now = self._clock.now()
        window_start, window_end = availability_window(branch, on_date)
        busy_intervals = await self._repository.list_active_appointment_intervals(
            branch.branch_id,
            service.service_id,
            window_start,
            window_end,
        )
        slots = generate_available_slots(
            branch=branch,
            service=service,
            on_date=on_date,
            busy_intervals=busy_intervals,
            now=now,
            slot_interval_minutes=self._slot_interval_minutes,
        )
        return Availability(
            branch_id=branch.branch_id,
            service_id=service.service_id,
            on_date=on_date,
            timezone=branch.timezone,
            slots=slots,
        )

    async def get_appointment(self, appointment_id: str) -> Appointment:
        normalized_id = validate_identifier(appointment_id, field_name="appointment_id")
        appointment = await self._repository.get_appointment(normalized_id)
        if appointment is None:
            _raise_not_found(
                ErrorCode.APPOINTMENT_NOT_FOUND,
                entity="appointment",
                appointment_id=normalized_id,
            )
        return appointment

    async def create_appointment(
        self,
        command: CreateAppointmentCommand,
    ) -> AppointmentWriteOutcome:
        require_confirmed(command)
        now = self._clock.now()
        require_future(command.start_at, now=now, field_name="start_at")
        fingerprint = command_fingerprint("create_appointment", command)

        customer = await self._repository.get_customer(command.customer_id)
        if customer is None:
            _raise_not_found(
                ErrorCode.CUSTOMER_NOT_FOUND,
                entity="customer",
                customer_id=command.customer_id,
            )
        vehicle = await self._repository.get_vehicle(command.vehicle_id)
        if vehicle is None:
            _raise_not_found(
                ErrorCode.VEHICLE_NOT_FOUND,
                entity="vehicle",
                vehicle_id=command.vehicle_id,
            )
        require_vehicle_owner(vehicle, customer.customer_id)

        branch = await self._require_branch(command.branch_id)
        service = await self._require_service(command.service_id)
        require_supported_service(branch, service.service_id)
        require_slot_cadence(
            branch=branch,
            start_at=command.start_at,
            slot_interval_minutes=self._slot_interval_minutes,
        )
        require_within_opening_hours(
            branch=branch,
            service=service,
            start_at=command.start_at,
        )
        return await self._repository.create_appointment(command, fingerprint)

    async def reschedule_appointment(
        self,
        command: RescheduleAppointmentCommand,
    ) -> AppointmentWriteOutcome:
        require_confirmed(command)
        now = self._clock.now()
        require_future(command.new_start_at, now=now, field_name="new_start_at")
        fingerprint = command_fingerprint("reschedule_appointment", command)

        appointment = await self.get_appointment(command.appointment_id)
        branch = await self._require_branch(appointment.branch_id)
        service = await self._require_service(appointment.service_id)
        require_supported_service(branch, service.service_id)
        require_slot_cadence(
            branch=branch,
            start_at=command.new_start_at,
            slot_interval_minutes=self._slot_interval_minutes,
        )
        require_within_opening_hours(
            branch=branch,
            service=service,
            start_at=command.new_start_at,
        )
        return await self._repository.reschedule_appointment(command, fingerprint)

    async def cancel_appointment(
        self,
        command: CancelAppointmentCommand,
    ) -> AppointmentWriteOutcome:
        require_confirmed(command)
        fingerprint = command_fingerprint("cancel_appointment", command)
        await self.get_appointment(command.appointment_id)
        return await self._repository.cancel_appointment(command, fingerprint)

    async def _require_branch(self, branch_id: str) -> Branch:
        branch = await self._repository.get_branch(branch_id)
        if branch is None:
            _raise_not_found(
                ErrorCode.BRANCH_NOT_FOUND,
                entity="branch",
                branch_id=branch_id,
            )
        return branch

    async def _require_service(self, service_id: str) -> ServiceType:
        service = await self._repository.get_service(service_id)
        if service is None:
            _raise_not_found(
                ErrorCode.SERVICE_NOT_FOUND,
                entity="service",
                service_id=service_id,
            )
        return service


def _raise_not_found(
    code: ErrorCode,
    *,
    entity: str,
    **details: object,
) -> Never:
    raise EntityNotFoundError(
        code,
        f"{entity} was not found",
        details={"entity": entity, **details},
    )


def domain_error_code(error: Exception) -> ErrorCode | None:
    """Return a stable code for expected domain errors."""

    return error.code if isinstance(error, DomainError) else None
