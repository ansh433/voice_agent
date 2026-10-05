"""Read-only LiveKit tool adapters over the deterministic business service."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date
from time import perf_counter
from typing import Protocol

from livekit.agents import ToolError, function_tool, llm

from domain import BusinessService, DomainError, ErrorCode

ANDHERI_BRANCH_ID = "bra_001"
ANDHERI_SHOP_NAME = "MotorMitra Andheri East"
DEFAULT_TOOL_TIMEOUT_SECONDS = 2.0


class ToolEventLogger(Protocol):
    """Minimal structured-event logger used by tool adapters."""

    def emit(self, event: str, **fields: object) -> None: ...


async def _execute_tool[T](
    operation: str,
    call: Callable[[], Awaitable[T]],
    event_logger: ToolEventLogger,
    *,
    timeout_seconds: float,
) -> T:
    """Execute one bounded read and translate expected failures safely."""
    started_at = perf_counter()
    event_logger.emit("tool_started", operation=operation)
    try:
        async with asyncio.timeout(timeout_seconds):
            result = await call()
    except TimeoutError as error:
        event_logger.emit(
            "tool_failed",
            operation=operation,
            error_code="timeout",
            duration_ms=round((perf_counter() - started_at) * 1_000, 2),
        )
        raise ToolError(
            "The service desk information is temporarily unavailable. Please try again."
        ) from error
    except DomainError as error:
        event_logger.emit(
            "tool_failed",
            operation=operation,
            error_code=error.code.value,
            duration_ms=round((perf_counter() - started_at) * 1_000, 2),
        )
        raise ToolError(_safe_domain_message(error)) from error
    except Exception as error:
        event_logger.emit(
            "tool_failed",
            operation=operation,
            error_code="unexpected_error",
            error_type=type(error).__name__,
            duration_ms=round((perf_counter() - started_at) * 1_000, 2),
        )
        raise

    event_logger.emit(
        "tool_completed",
        operation=operation,
        duration_ms=round((perf_counter() - started_at) * 1_000, 2),
    )
    return result


def _safe_domain_message(error: DomainError) -> str:
    if error.code is ErrorCode.CUSTOMER_NOT_FOUND:
        return "No customer was found for that phone number. Ask the user to check the number."
    if error.code is ErrorCode.SERVICE_NOT_FOUND:
        return "That service could not be found. Offer to list the available services."
    if error.code in {ErrorCode.INVALID_DATE, ErrorCode.START_TIME_NOT_FUTURE}:
        return "That date cannot be checked. Ask for a current or future date."
    if error.code is ErrorCode.STORAGE_UNAVAILABLE:
        return "The service desk information is temporarily unavailable. Please try again."
    return "The service desk could not complete that lookup. Ask the user to verify the details."


def create_read_tools(
    service: BusinessService,
    event_logger: ToolEventLogger,
    *,
    timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS,
) -> list[llm.Tool | llm.Toolset]:
    """Create the read-only tools available to the MotorMitra voice agent."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    @function_tool()
    async def lookup_customer(phone: str) -> dict[str, object]:
        """Look up an existing MotorMitra customer by phone number.

        Args:
            phone: Customer phone number, preferably including the +91 country code.
        """
        customer = await _execute_tool(
            "lookup_customer",
            lambda: service.lookup_customer(phone),
            event_logger,
            timeout_seconds=timeout_seconds,
        )
        return {
            "found": True,
            "customer_id": customer.customer_id,
            "full_name": customer.full_name,
            "preferred_language": customer.preferred_language.value,
        }

    @function_tool()
    async def list_services() -> dict[str, object]:
        """List services currently offered by the single MotorMitra Andheri East shop."""
        services = await _execute_tool(
            "list_services",
            lambda: service.list_services(ANDHERI_BRANCH_ID),
            event_logger,
            timeout_seconds=timeout_seconds,
        )
        return {
            "shop": ANDHERI_SHOP_NAME,
            "services": [
                {
                    "service_id": item.service_id,
                    "name": item.name,
                    "duration_minutes": item.duration_minutes,
                    "description": item.description,
                    "base_price_inr": format(item.base_price, ".2f"),
                }
                for item in services
            ],
        }

    @function_tool()
    async def check_available_slots(
        service_id: str,
        appointment_date: str,
    ) -> dict[str, object]:
        """Check appointment slots for a service at MotorMitra Andheri East.

        Args:
            service_id: Stable service ID returned by list_services.
            appointment_date: Requested shop-local date in YYYY-MM-DD format.
        """
        try:
            requested_date = date.fromisoformat(appointment_date)
        except ValueError as error:
            event_logger.emit(
                "tool_failed",
                operation="check_available_slots",
                error_code="invalid_date_format",
            )
            raise ToolError("Use a calendar date in YYYY-MM-DD format.") from error

        availability = await _execute_tool(
            "check_available_slots",
            lambda: service.check_available_slots(
                ANDHERI_BRANCH_ID,
                service_id,
                requested_date,
            ),
            event_logger,
            timeout_seconds=timeout_seconds,
        )
        return {
            "service_id": availability.service_id,
            "date": availability.on_date.isoformat(),
            "timezone": availability.timezone,
            "available_slots": [
                {
                    "start_at": slot.start_at.isoformat(),
                    "end_at": slot.end_at.isoformat(),
                }
                for slot in availability.slots
            ],
        }

    return [lookup_customer, list_services, check_available_slots]
