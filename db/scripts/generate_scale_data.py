#!/usr/bin/env python3
"""Emit deterministic PostgreSQL load data without changing the base fixture."""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

REFERENCE_TIME = datetime(2026, 1, 15, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
DEFAULT_SEED = 20260115
BATCH_SIZE = 500

FIRST_NAMES = (
    "Aarav",
    "Aditi",
    "Diya",
    "Ishaan",
    "Kabir",
    "Meera",
    "Neha",
    "Rohan",
    "Tara",
    "Zoya",
)
LAST_NAMES = (
    "Bose",
    "Gupta",
    "Iyer",
    "Jain",
    "Kulkarni",
    "Mehta",
    "Nair",
    "Patil",
    "Shah",
    "Verma",
)
VEHICLES = (
    ("Maruti Suzuki", "Baleno"),
    ("Hyundai", "Creta"),
    ("Tata", "Nexon"),
    ("Mahindra", "XUV300"),
    ("Honda", "City"),
    ("Toyota", "Glanza"),
    ("Kia", "Seltos"),
    ("Renault", "Kiger"),
)
SERVICE_DURATIONS = (60, 180, 90, 120, 45, 60)
LANGUAGES = ("en", "hi", "hinglish")
INACTIVE_STATUSES = ("completed", "completed", "completed", "cancelled", "no_show")


def sql_text(value: str) -> str:
    """Return a quoted SQL literal for controlled synthetic values."""
    return "'" + value.replace("'", "''") + "'"


def sql_timestamp(value: datetime) -> str:
    """Return an explicit timezone-aware PostgreSQL timestamp literal."""
    return f"timestamptz {sql_text(value.isoformat())}"


def batched(values: Sequence[str], size: int = BATCH_SIZE) -> Iterable[Sequence[str]]:
    """Yield bounded batches to keep generated statements manageable."""
    for start in range(0, len(values), size):
        yield values[start : start + size]


def emit_insert(table: str, columns: str, rows: Sequence[str]) -> None:
    """Print idempotent batched INSERT statements."""
    for batch in batched(rows):
        sys.stdout.write(f"INSERT INTO {table} ({columns}) VALUES\n")
        sys.stdout.write(",\n".join(batch))
        sys.stdout.write("\nON CONFLICT DO NOTHING;\n\n")


def customer_rows(count: int, generator: random.Random) -> list[str]:
    rows: list[str] = []
    for number in range(1, count + 1):
        first_name = generator.choice(FIRST_NAMES)
        last_name = generator.choice(LAST_NAMES)
        values = (
            f"load_cus_{number:08d}",
            f"{first_name} {last_name}",
            f"+9101{number:08d}",
            generator.choice(LANGUAGES),
        )
        rows.append("    (" + ", ".join(sql_text(value) for value in values) + ")")
    return rows


def vehicle_rows(count: int, generator: random.Random) -> list[str]:
    rows: list[str] = []
    for number in range(1, count + 1):
        make, model = generator.choice(VEHICLES)
        values = (
            sql_text(f"load_veh_{number:08d}"),
            sql_text(f"load_cus_{number:08d}"),
            sql_text(f"LOAD-MH-{number:08d}"),
            sql_text(make),
            sql_text(model),
            str(generator.randint(2012, 2025)),
        )
        rows.append("    (" + ", ".join(values) + ")")
    return rows


def appointment_rows(
    count: int,
    customer_count: int,
    generator: random.Random,
) -> list[str]:
    rows: list[str] = []
    active_number = 0
    for number in range(1, count + 1):
        customer_number = ((number - 1) % customer_count) + 1
        branch_number = 1
        service_number = generator.randint(1, 6)
        is_active = generator.random() < 0.10
        if is_active:
            active_number += 1
            status = "scheduled" if active_number % 2 else "confirmed"
            start_at = REFERENCE_TIME + timedelta(days=60 + active_number)
        else:
            status = generator.choice(INACTIVE_STATUSES)
            start_at = (
                REFERENCE_TIME
                - timedelta(days=generator.randint(1, 730))
                + timedelta(hours=generator.randint(-2, 6))
            )
        end_at = start_at + timedelta(minutes=SERVICE_DURATIONS[service_number - 1])
        created_at = REFERENCE_TIME - timedelta(days=800) + timedelta(seconds=number)
        values = (
            sql_text(f"load_apt_{number:09d}"),
            sql_text(f"load_cus_{customer_number:08d}"),
            sql_text(f"load_veh_{customer_number:08d}"),
            sql_text(f"bra_{branch_number:03d}"),
            sql_text(f"svc_{service_number:03d}"),
            sql_timestamp(start_at),
            sql_timestamp(end_at),
            sql_text(status),
            sql_text(f"load-create-{number:09d}"),
            "1",
            sql_timestamp(created_at),
            sql_timestamp(created_at),
        )
        rows.append("    (" + ", ".join(values) + ")")
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customers", type=int, default=1_000)
    parser.add_argument("--appointments", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    if args.customers < 1 or args.customers > 10_000_000:
        parser.error("--customers must be between 1 and 10000000")
    if args.appointments < 0 or args.appointments > 10_000_000:
        parser.error("--appointments must be between 0 and 10000000")
    return args


def main() -> None:
    args = parse_args()
    generator = random.Random(args.seed)
    sys.stdout.write("\\set ON_ERROR_STOP on\nBEGIN;\n\n")
    emit_insert(
        "customers",
        "customer_id, full_name, phone, preferred_language",
        customer_rows(args.customers, generator),
    )
    emit_insert(
        "vehicles",
        "vehicle_id, customer_id, registration_number, make, model, year",
        vehicle_rows(args.customers, generator),
    )
    emit_insert(
        "appointments",
        (
            "appointment_id, customer_id, vehicle_id, branch_id, service_id, "
            "start_at, end_at, status, idempotency_key, version, created_at, updated_at"
        ),
        appointment_rows(args.appointments, args.customers, generator),
    )
    sys.stdout.write("COMMIT;\n")


if __name__ == "__main__":
    main()
