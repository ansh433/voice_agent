"""Optional Langfuse OpenTelemetry export for LiveKit voice sessions."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from langfuse import Langfuse
from livekit.agents.telemetry import set_tracer_provider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util.types import AttributeValue

from configuration import LangfuseSettings, load_langfuse_settings

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LangfuseTraceRuntime:
    """Own the tracer provider and exporter created for one agent session."""

    client: Langfuse
    tracer_provider: TracerProvider

    def flush(self) -> None:
        """Flush buffered telemetry before the LiveKit job exits."""
        self.tracer_provider.force_flush()
        self.client.flush()


def setup_langfuse(
    metadata: dict[str, AttributeValue],
    *,
    settings: LangfuseSettings | None = None,
) -> LangfuseTraceRuntime | None:
    """Configure optional Langfuse export before an AgentSession starts."""
    resolved_settings = settings or load_langfuse_settings()
    public_key = resolved_settings.langfuse_public_key
    secret_key = resolved_settings.langfuse_secret_key
    if public_key is None and secret_key is None:
        return None
    if public_key is None or secret_key is None:
        LOGGER.warning("Langfuse tracing disabled because both credentials are required")
        return None

    tracer_provider = TracerProvider()
    set_tracer_provider(
        tracer_provider,
        metadata=metadata,
        allow_pii=resolved_settings.langfuse_capture_pii,
    )
    client = Langfuse(
        public_key=public_key.get_secret_value(),
        secret_key=secret_key.get_secret_value(),
        base_url=resolved_settings.langfuse_base_url,
        tracer_provider=tracer_provider,
        should_export_span=lambda _span: True,
    )
    return LangfuseTraceRuntime(client=client, tracer_provider=tracer_provider)
