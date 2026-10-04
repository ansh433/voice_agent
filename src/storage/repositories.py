"""Concrete asyncpg implementation of the business repository contract."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from functools import wraps
from types import CoroutineType
from typing import Any, NoReturn
from uuid import uuid4

import asyncpg
from asyncpg.pool import PoolConnectionProxy

from domain.errors import (
    ConflictError,
    DomainError,
    EntityNotFoundError,
    ErrorCode,
    StorageUnavailableError,
)
from domain.models import (
    Appointment,
    AppointmentInterval,
    AppointmentStatus,
    AppointmentWriteOutcome,
    Branch,
    CancelAppointmentCommand,
    ConfirmedWriteCommand,
    CreateAppointmentCommand,
    Customer,
    OpeningHours,
    RescheduleAppointmentCommand,
    ServiceType,
    Vehicle,
    WriteDisposition,
)

from .db import Database, DatabaseNotStartedError


def _translate_storage_errors[**P, R](
    function: Callable[P, CoroutineType[Any, Any, R]],
) -> Callable[P, CoroutineType[Any, Any, R]]:
    """Keep driver, lifecycle, and timeout failures behind the domain boundary."""

    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await function(*args, **kwargs)
        except DomainError:
            raise
        except (
            asyncpg.PostgresError,
            DatabaseNotStartedError,
            TimeoutError,
            OSError,
        ) as error:
            raise StorageUnavailableError() from error

    return wrapped


class PostgresBusinessRepository:
    """Persist and retrieve business state using one bounded asyncpg pool."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @_translate_storage_errors
    async def lookup_customer_by_phone(self, phone: str) -> Customer | None:
        async with self._database.connection() as connection:
            row = await connection.fetchrow(
                """
                SELECT customer_id, full_name, phone, preferred_language
                FROM customers
                WHERE phone = $1
                """,
                phone,
            )
        return _customer_from_row(row) if row is not None else None

    @_translate_storage_errors
    async def list_branches(self, city: str | None = None) -> Sequence[Branch]:
        async with self._database.connection() as connection:
            rows = await connection.fetch(
                """
                SELECT branch_id, name, locality, city, timezone
                FROM branches
                WHERE ($1::text IS NULL OR lower(city) = lower($1))
                ORDER BY name, branch_id
                """,
                city,
            )
            return await _hydrate_branches(connection, rows)

    @_translate_storage_errors
    async def list_services(self, branch_id: str | None = None) -> Sequence[ServiceType]:
        async with self._database.connection() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    service.service_id,
                    service.name,
                    service.duration_minutes,
                    service.description,
                    service.base_price
                FROM service_types AS service
                WHERE $1::text IS NULL
                    OR EXISTS (
                        SELECT 1
                        FROM branch_services AS supported
                        WHERE supported.branch_id = $1
                          AND supported.service_id = service.service_id
                          AND supported.is_active
                    )
                ORDER BY service.name, service.service_id
                """,
                branch_id,
            )
        return tuple(_service_from_row(row) for row in rows)

    @_translate_storage_errors
    async def get_customer(self, customer_id: str) -> Customer | None:
        async with self._database.connection() as connection:
            row = await connection.fetchrow(
                """
                SELECT customer_id, full_name, phone, preferred_language
                FROM customers
                WHERE customer_id = $1
                """,
                customer_id,
            )
        return _customer_from_row(row) if row is not None else None

    @_translate_storage_errors
    async def get_vehicle(self, vehicle_id: str) -> Vehicle | None:
        async with self._database.connection() as connection:
            row = await connection.fetchrow(
                """
                SELECT vehicle_id, customer_id, registration_number, make, model, year
                FROM vehicles
                WHERE vehicle_id = $1
                """,
                vehicle_id,
            )
        return _vehicle_from_row(row) if row is not None else None

    @_translate_storage_errors
    async def get_branch(self, branch_id: str) -> Branch | None:
        async with self._database.connection() as connection:
            rows = await connection.fetch(
                """
                SELECT branch_id, name, locality, city, timezone
                FROM branches
                WHERE branch_id = $1
                """,
                branch_id,
            )
            branches = await _hydrate_branches(connection, rows)
        return branches[0] if branches else None

    @_translate_storage_errors
    async def get_service(self, service_id: str) -> ServiceType | None:
        async with self._database.connection() as connection:
            row = await connection.fetchrow(
                """
                SELECT service_id, name, duration_minutes, description, base_price
                FROM service_types
                WHERE service_id = $1
                """,
                service_id,
            )
        return _service_from_row(row) if row is not None else None

    @_translate_storage_errors
    async def get_appointment(self, appointment_id: str) -> Appointment | None:
        async with self._database.connection() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    appointment_id,
                    customer_id,
                    vehicle_id,
                    branch_id,
                    service_id,
                    start_at,
                    end_at,
                    status,
                    idempotency_key,
                    version,
                    created_at,
                    updated_at
                FROM appointments
                WHERE appointment_id = $1
                """,
                appointment_id,
            )
        return _appointment_from_row(row) if row is not None else None

    @_translate_storage_errors
    async def list_active_appointment_intervals(
        self,
        branch_id: str,
        service_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Sequence[AppointmentInterval]:
        async with self._database.connection() as connection:
            rows = await connection.fetch(
                """
                SELECT start_at, end_at
                FROM appointments
                WHERE branch_id = $1
                  AND service_id = $2
                  AND status IN ('scheduled', 'confirmed')
                  AND start_at < $4
                  AND end_at > $3
                ORDER BY start_at, end_at
                """,
                branch_id,
                service_id,
                window_start,
                window_end,
            )
        return tuple(
            AppointmentInterval(start_at=row["start_at"], end_at=row["end_at"]) for row in rows
        )

    @_translate_storage_errors
    async def create_appointment(
        self,
        command: CreateAppointmentCommand,
        request_fingerprint: str,
    ) -> AppointmentWriteOutcome:
        try:
            async with self._database.transaction() as connection:
                replay = await _claim_command(
                    connection,
                    operation="create",
                    command=command,
                    request_fingerprint=request_fingerprint,
                )
                if replay is not None:
                    return replay

                duration_minutes = await _validate_create_references(connection, command)
                appointment_id = f"apt_{uuid4().hex}"
                row = await connection.fetchrow(
                    """
                    INSERT INTO appointments (
                        appointment_id,
                        customer_id,
                        vehicle_id,
                        branch_id,
                        service_id,
                        start_at,
                        end_at,
                        status,
                        idempotency_key
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'scheduled', $8)
                    RETURNING
                        appointment_id,
                        customer_id,
                        vehicle_id,
                        branch_id,
                        service_id,
                        start_at,
                        end_at,
                        status,
                        idempotency_key,
                        version,
                        created_at,
                        updated_at
                    """,
                    appointment_id,
                    command.customer_id,
                    command.vehicle_id,
                    command.branch_id,
                    command.service_id,
                    command.start_at,
                    command.start_at + timedelta(minutes=duration_minutes),
                    command.idempotency_key,
                )
                assert row is not None
                outcome = AppointmentWriteOutcome(
                    disposition=WriteDisposition.CREATED,
                    appointment=_appointment_from_row(row),
                    request_fingerprint=request_fingerprint,
                )
                await _complete_command(connection, command.idempotency_key, outcome)
                return outcome
        except asyncpg.PostgresError as error:
            _raise_mapped_database_error(error)

    @_translate_storage_errors
    async def reschedule_appointment(
        self,
        command: RescheduleAppointmentCommand,
        request_fingerprint: str,
    ) -> AppointmentWriteOutcome:
        try:
            async with self._database.transaction() as connection:
                replay = await _claim_command(
                    connection,
                    operation="reschedule",
                    command=command,
                    request_fingerprint=request_fingerprint,
                )
                if replay is not None:
                    return replay

                current_row = await connection.fetchrow(
                    """
                    SELECT
                        appointment.appointment_id,
                        appointment.customer_id,
                        appointment.vehicle_id,
                        appointment.branch_id,
                        appointment.service_id,
                        appointment.start_at,
                        appointment.end_at,
                        appointment.status,
                        appointment.idempotency_key,
                        appointment.version,
                        appointment.created_at,
                        appointment.updated_at,
                        service.duration_minutes
                    FROM appointments AS appointment
                    JOIN service_types AS service
                      ON service.service_id = appointment.service_id
                    WHERE appointment.appointment_id = $1
                    FOR UPDATE OF appointment
                    """,
                    command.appointment_id,
                )
                if current_row is None:
                    raise EntityNotFoundError(
                        ErrorCode.APPOINTMENT_NOT_FOUND,
                        "appointment was not found",
                        details={"appointment_id": command.appointment_id},
                    )
                if current_row["status"] not in {
                    AppointmentStatus.SCHEDULED.value,
                    AppointmentStatus.CONFIRMED.value,
                }:
                    raise ConflictError(
                        ErrorCode.INVALID_APPOINTMENT_STATE,
                        "only an active appointment can be rescheduled",
                        details={"appointment_id": command.appointment_id},
                    )
                _require_expected_version(current_row, command.expected_version)

                new_end_at = command.new_start_at + timedelta(
                    minutes=current_row["duration_minutes"]
                )
                changed_row = await connection.fetchrow(
                    """
                    UPDATE appointments
                    SET start_at = $2,
                        end_at = $3,
                        version = version + 1
                    WHERE appointment_id = $1
                    RETURNING
                        appointment_id,
                        customer_id,
                        vehicle_id,
                        branch_id,
                        service_id,
                        start_at,
                        end_at,
                        status,
                        idempotency_key,
                        version,
                        created_at,
                        updated_at
                    """,
                    command.appointment_id,
                    command.new_start_at,
                    new_end_at,
                )
                assert changed_row is not None
                outcome = AppointmentWriteOutcome(
                    disposition=WriteDisposition.RESCHEDULED,
                    appointment=_appointment_from_row(changed_row),
                    request_fingerprint=request_fingerprint,
                )
                await _complete_command(connection, command.idempotency_key, outcome)
                return outcome
        except asyncpg.PostgresError as error:
            _raise_mapped_database_error(error)

    @_translate_storage_errors
    async def cancel_appointment(
        self,
        command: CancelAppointmentCommand,
        request_fingerprint: str,
    ) -> AppointmentWriteOutcome:
        async with self._database.transaction() as connection:
            replay = await _claim_command(
                connection,
                operation="cancel",
                command=command,
                request_fingerprint=request_fingerprint,
            )
            if replay is not None:
                return replay

            current_row = await connection.fetchrow(
                """
                SELECT
                    appointment_id,
                    customer_id,
                    vehicle_id,
                    branch_id,
                    service_id,
                    start_at,
                    end_at,
                    status,
                    idempotency_key,
                    version,
                    created_at,
                    updated_at
                FROM appointments
                WHERE appointment_id = $1
                FOR UPDATE
                """,
                command.appointment_id,
            )
            if current_row is None:
                raise EntityNotFoundError(
                    ErrorCode.APPOINTMENT_NOT_FOUND,
                    "appointment was not found",
                    details={"appointment_id": command.appointment_id},
                )

            if current_row["status"] == AppointmentStatus.CANCELLED.value:
                outcome = AppointmentWriteOutcome(
                    disposition=WriteDisposition.ALREADY_CANCELLED,
                    appointment=_appointment_from_row(current_row),
                    request_fingerprint=request_fingerprint,
                )
                await _complete_command(connection, command.idempotency_key, outcome)
                return outcome
            if current_row["status"] not in {
                AppointmentStatus.SCHEDULED.value,
                AppointmentStatus.CONFIRMED.value,
            }:
                raise ConflictError(
                    ErrorCode.INVALID_APPOINTMENT_STATE,
                    "only an active appointment can be cancelled",
                    details={"appointment_id": command.appointment_id},
                )
            _require_expected_version(current_row, command.expected_version)

            changed_row = await connection.fetchrow(
                """
                UPDATE appointments
                SET status = 'cancelled',
                    version = version + 1
                WHERE appointment_id = $1
                RETURNING
                    appointment_id,
                    customer_id,
                    vehicle_id,
                    branch_id,
                    service_id,
                    start_at,
                    end_at,
                    status,
                    idempotency_key,
                    version,
                    created_at,
                    updated_at
                """,
                command.appointment_id,
            )
            assert changed_row is not None
            outcome = AppointmentWriteOutcome(
                disposition=WriteDisposition.CANCELLED,
                appointment=_appointment_from_row(changed_row),
                request_fingerprint=request_fingerprint,
            )
            await _complete_command(connection, command.idempotency_key, outcome)
            return outcome


async def _claim_command(
    connection: PoolConnectionProxy[asyncpg.Record],
    *,
    operation: str,
    command: ConfirmedWriteCommand,
    request_fingerprint: str,
) -> AppointmentWriteOutcome | None:
    claimed = await connection.fetchval(
        """
        INSERT INTO appointment_commands (
            idempotency_key,
            operation,
            request_hash,
            request_payload,
            status
        )
        VALUES ($1, $2, $3, $4::jsonb, 'pending')
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING true
        """,
        command.idempotency_key,
        operation,
        request_fingerprint,
        command.model_dump_json(),
    )
    if claimed:
        return None

    existing = await connection.fetchrow(
        """
        SELECT operation, request_hash, response_payload, status, error_code
        FROM appointment_commands
        WHERE idempotency_key = $1
        FOR UPDATE
        """,
        command.idempotency_key,
    )
    if existing is None:
        raise RuntimeError("idempotency command disappeared during replay")
    if existing["operation"] != operation or existing["request_hash"] != request_fingerprint:
        raise ConflictError(
            ErrorCode.IDEMPOTENCY_KEY_REUSED,
            "idempotency key was already used for another request",
            details={"idempotency_key": command.idempotency_key},
        )
    if existing["status"] == "succeeded" and existing["response_payload"] is not None:
        return _outcome_from_payload(existing["response_payload"])
    if existing["status"] == "failed":
        raw_code = existing["error_code"]
        code = (
            ErrorCode(raw_code)
            if raw_code in ErrorCode._value2member_map_
            else ErrorCode.SLOT_CONFLICT
        )
        raise DomainError(code, "the original request failed")
    raise RuntimeError("idempotency command has no terminal outcome")


async def _complete_command(
    connection: PoolConnectionProxy[asyncpg.Record],
    idempotency_key: str,
    outcome: AppointmentWriteOutcome,
) -> None:
    await connection.execute(
        """
        UPDATE appointment_commands
        SET appointment_id = $2,
            response_payload = $3::jsonb,
            status = 'succeeded'
        WHERE idempotency_key = $1
        """,
        idempotency_key,
        outcome.appointment.appointment_id,
        outcome.model_dump_json(),
    )


async def _validate_create_references(
    connection: PoolConnectionProxy[asyncpg.Record],
    command: CreateAppointmentCommand,
) -> int:
    customer_exists = await connection.fetchval(
        "SELECT EXISTS(SELECT 1 FROM customers WHERE customer_id = $1)",
        command.customer_id,
    )
    if not customer_exists:
        raise EntityNotFoundError(
            ErrorCode.CUSTOMER_NOT_FOUND,
            "customer was not found",
            details={"customer_id": command.customer_id},
        )

    vehicle_owner = await connection.fetchval(
        "SELECT customer_id FROM vehicles WHERE vehicle_id = $1",
        command.vehicle_id,
    )
    if vehicle_owner is None:
        raise EntityNotFoundError(
            ErrorCode.VEHICLE_NOT_FOUND,
            "vehicle was not found",
            details={"vehicle_id": command.vehicle_id},
        )
    if vehicle_owner != command.customer_id:
        raise ConflictError(
            ErrorCode.VEHICLE_CUSTOMER_MISMATCH,
            "vehicle does not belong to the requested customer",
            details={
                "vehicle_id": command.vehicle_id,
                "customer_id": command.customer_id,
            },
        )

    branch_exists = await connection.fetchval(
        "SELECT EXISTS(SELECT 1 FROM branches WHERE branch_id = $1)",
        command.branch_id,
    )
    if not branch_exists:
        raise EntityNotFoundError(
            ErrorCode.BRANCH_NOT_FOUND,
            "branch was not found",
            details={"branch_id": command.branch_id},
        )

    duration_minutes = await connection.fetchval(
        "SELECT duration_minutes FROM service_types WHERE service_id = $1",
        command.service_id,
    )
    if duration_minutes is None:
        raise EntityNotFoundError(
            ErrorCode.SERVICE_NOT_FOUND,
            "service was not found",
            details={"service_id": command.service_id},
        )

    supported = await connection.fetchval(
        """
        SELECT EXISTS(
            SELECT 1
            FROM branch_services
            WHERE branch_id = $1
              AND service_id = $2
              AND is_active
        )
        """,
        command.branch_id,
        command.service_id,
    )
    if not supported:
        raise ConflictError(
            ErrorCode.UNSUPPORTED_SERVICE,
            "branch does not support the requested service",
            details={
                "branch_id": command.branch_id,
                "service_id": command.service_id,
            },
        )
    return int(duration_minutes)


def _require_expected_version(row: asyncpg.Record, expected_version: int) -> None:
    actual_version = int(row["version"])
    if actual_version != expected_version:
        raise ConflictError(
            ErrorCode.VERSION_CONFLICT,
            "appointment was changed by another request",
            details={
                "expected_version": expected_version,
                "actual_version": actual_version,
            },
        )


def _outcome_from_payload(payload: object) -> AppointmentWriteOutcome:
    if isinstance(payload, str):
        return AppointmentWriteOutcome.model_validate_json(payload)
    return AppointmentWriteOutcome.model_validate(payload)


def _raise_mapped_database_error(error: asyncpg.PostgresError) -> NoReturn:
    constraint_name = getattr(error, "constraint_name", None)
    if constraint_name in {
        "appointments_branch_service_no_overlap",
        "appointments_vehicle_no_overlap",
    }:
        raise ConflictError(
            ErrorCode.SLOT_CONFLICT,
            "appointment conflicts with an existing active appointment",
        ) from error
    if constraint_name == "appointments_vehicle_owned_by_customer":
        raise ConflictError(
            ErrorCode.VEHICLE_CUSTOMER_MISMATCH,
            "vehicle does not belong to the requested customer",
        ) from error
    if constraint_name == "appointments_supported_branch_service":
        raise ConflictError(
            ErrorCode.UNSUPPORTED_SERVICE,
            "branch does not support the requested service",
        ) from error
    if constraint_name in {
        "appointments_idempotency_key_key",
        "appointment_commands_pkey",
    }:
        raise ConflictError(
            ErrorCode.IDEMPOTENCY_KEY_REUSED,
            "idempotency key was already used for another request",
        ) from error
    raise error


async def _hydrate_branches(
    connection: PoolConnectionProxy[asyncpg.Record],
    rows: Sequence[asyncpg.Record],
) -> tuple[Branch, ...]:
    if not rows:
        return ()

    branch_ids = [str(row["branch_id"]) for row in rows]
    hours_rows = await connection.fetch(
        """
        SELECT branch_id, weekday, opens_at, closes_at
        FROM branch_hours
        WHERE branch_id = ANY($1::text[])
          AND NOT is_closed
        ORDER BY branch_id, weekday
        """,
        branch_ids,
    )
    service_rows = await connection.fetch(
        """
        SELECT branch_id, service_id
        FROM branch_services
        WHERE branch_id = ANY($1::text[])
          AND is_active
        ORDER BY branch_id, service_id
        """,
        branch_ids,
    )

    hours_by_branch: defaultdict[str, list[OpeningHours]] = defaultdict(list)
    for row in hours_rows:
        hours_by_branch[str(row["branch_id"])].append(
            OpeningHours(
                weekday=row["weekday"],
                opens_at=row["opens_at"],
                closes_at=row["closes_at"],
            )
        )

    services_by_branch: defaultdict[str, list[str]] = defaultdict(list)
    for row in service_rows:
        services_by_branch[str(row["branch_id"])].append(str(row["service_id"]))

    return tuple(
        Branch(
            branch_id=row["branch_id"],
            name=row["name"],
            locality=row["locality"],
            city=row["city"],
            timezone=row["timezone"],
            opening_hours=tuple(hours_by_branch[str(row["branch_id"])]),
            supported_service_ids=tuple(services_by_branch[str(row["branch_id"])]),
        )
        for row in rows
    )


def _customer_from_row(row: asyncpg.Record) -> Customer:
    return Customer(
        customer_id=row["customer_id"],
        full_name=row["full_name"],
        phone=row["phone"],
        preferred_language=row["preferred_language"],
    )


def _vehicle_from_row(row: asyncpg.Record) -> Vehicle:
    return Vehicle(
        vehicle_id=row["vehicle_id"],
        customer_id=row["customer_id"],
        registration_number=row["registration_number"],
        make=row["make"],
        model=row["model"],
        year=row["year"],
    )


def _service_from_row(row: asyncpg.Record) -> ServiceType:
    return ServiceType(
        service_id=row["service_id"],
        name=row["name"],
        duration_minutes=row["duration_minutes"],
        description=row["description"],
        base_price=row["base_price"],
    )


def _appointment_from_row(row: asyncpg.Record) -> Appointment:
    return Appointment(
        appointment_id=row["appointment_id"],
        customer_id=row["customer_id"],
        vehicle_id=row["vehicle_id"],
        branch_id=row["branch_id"],
        service_id=row["service_id"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        status=row["status"],
        idempotency_key=row["idempotency_key"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
