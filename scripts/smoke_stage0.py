"""Exercise the Stage 0 public service against a disposable test database."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from domain import (
    CancelAppointmentCommand,
    CreateAppointmentCommand,
    DefaultBusinessService,
    FixedClock,
    RescheduleAppointmentCommand,
)
from storage import Database, PostgresBusinessRepository


def _test_database_url() -> str:
    database_url = os.environ.get("SMOKE_DATABASE_URL")
    if not database_url:
        raise RuntimeError("SMOKE_DATABASE_URL is required")
    database_name = unquote(urlparse(database_url).path).removeprefix("/")
    if not database_name.endswith("_test"):
        raise RuntimeError("smoke workflow refuses databases whose name does not end in '_test'")
    return database_url


async def main() -> None:
    """Create, reschedule, cancel, and replay one appointment command chain."""
    database = Database(_test_database_url())
    clock = FixedClock(datetime(2026, 1, 15, 10, tzinfo=ZoneInfo("Asia/Kolkata")))

    async with database:
        service = DefaultBusinessService(
            PostgresBusinessRepository(database),
            clock=clock,
        )
        customer = await service.lookup_customer("+91 00000 00001")
        availability = await service.check_available_slots(
            "bra_001",
            "svc_001",
            date(2026, 2, 10),
        )
        selected_slot = availability.slots[0]

        created = await service.create_appointment(
            CreateAppointmentCommand(
                customer_id=customer.customer_id,
                vehicle_id="veh_001",
                branch_id="bra_001",
                service_id="svc_001",
                start_at=selected_slot.start_at,
                confirmed=True,
                idempotency_key="smoke-create-001",
            )
        )
        rescheduled = await service.reschedule_appointment(
            RescheduleAppointmentCommand(
                appointment_id=created.appointment.appointment_id,
                new_start_at=selected_slot.start_at.replace(day=11),
                expected_version=created.appointment.version,
                confirmed=True,
                idempotency_key="smoke-reschedule-001",
            )
        )
        cancelled = await service.cancel_appointment(
            CancelAppointmentCommand(
                appointment_id=created.appointment.appointment_id,
                expected_version=rescheduled.appointment.version,
                confirmed=True,
                idempotency_key="smoke-cancel-001",
            )
        )
        replayed = await service.cancel_appointment(
            CancelAppointmentCommand(
                appointment_id=created.appointment.appointment_id,
                expected_version=rescheduled.appointment.version,
                confirmed=True,
                idempotency_key="smoke-cancel-001",
            )
        )

    print(
        json.dumps(
            {
                "customer_id": customer.customer_id,
                "slot_count": len(availability.slots),
                "appointment_id": created.appointment.appointment_id,
                "created": created.disposition,
                "rescheduled_version": rescheduled.appointment.version,
                "cancelled_version": cancelled.appointment.version,
                "replay": replayed.disposition,
                "final_status": replayed.appointment.status,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
