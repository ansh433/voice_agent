"""LiveKit voice-agent session lifecycle and composition."""

from __future__ import annotations

from uuid import uuid4

from livekit.agents import Agent, JobContext, vad

from configuration import (
    Settings,
    VoicePipelineSettings,
    load_settings,
    load_voice_pipeline_settings,
)
from domain import BusinessService, DefaultBusinessService
from observability.langfuse import LangfuseTraceRuntime, setup_langfuse
from storage import Database, PostgresBusinessRepository

from .events import SessionIdentifiers, VoiceEventLogger
from .pipeline import (
    DEFAULT_PROVIDER_FACTORIES,
    ProviderFactories,
    create_agent_session,
    create_voice_pipeline,
)
from .prompts import MOTOR_MITRA_INSTRUCTIONS, WELCOME_GREETING
from .tools import ToolEventLogger, create_read_tools

PREWARMED_VAD_KEY = "motor_mitra_silero_vad"


class Assistant(Agent):
    """MotorMitra assistant with the bounded read-only business tools."""

    def __init__(
        self,
        business_service: BusinessService,
        event_logger: ToolEventLogger,
    ) -> None:
        super().__init__(  # pyright: ignore[reportUnknownMemberType]
            instructions=MOTOR_MITRA_INSTRUCTIONS,
            tools=create_read_tools(business_service, event_logger),
        )


async def start_business_service(
    settings: Settings | None = None,
) -> tuple[BusinessService, Database]:
    """Start the session-scoped PostgreSQL service used by voice tools."""
    resolved_settings = settings or load_settings()
    database = Database(
        str(resolved_settings.database_url),
        min_pool_size=resolved_settings.database_pool_min_size,
        max_pool_size=resolved_settings.database_pool_max_size,
        acquire_timeout_seconds=resolved_settings.database_acquire_timeout_seconds,
        query_timeout_seconds=resolved_settings.database_command_timeout_seconds,
    )
    await database.start()
    return DefaultBusinessService(PostgresBusinessRepository(database)), database


def get_prewarmed_vad(ctx: JobContext) -> vad.VAD:
    """Return the process-scoped Silero model or fail with an actionable error."""
    vad_model = ctx.proc.userdata.get(PREWARMED_VAD_KEY)
    if not isinstance(vad_model, vad.VAD):
        raise RuntimeError("Silero VAD was not prewarmed in the LiveKit worker process")
    return vad_model


async def run_voice_session(
    ctx: JobContext,
    *,
    settings: VoicePipelineSettings | None = None,
    factories: ProviderFactories = DEFAULT_PROVIDER_FACTORIES,
    business_service: BusinessService | None = None,
) -> None:
    """Start MotorMitra, greet the caller, and register safe provider cleanup."""
    identifiers = SessionIdentifiers(
        session_id=ctx.job.id,
        correlation_id=uuid4().hex,
    )
    event_logger = VoiceEventLogger(identifiers)
    trace_runtime: LangfuseTraceRuntime | None = None
    try:
        trace_runtime = setup_langfuse(
            {
                "langfuse.session.id": ctx.room.name,
                "langfuse.tags": ["livekit", "motor-mitra", "voice-agent"],
            }
        )
        if trace_runtime is not None:
            event_logger.emit("langfuse_tracing_enabled")
    except Exception as error:
        event_logger.emit("langfuse_setup_failed", error_type=type(error).__name__)

    database: Database | None = None
    if business_service is None:
        try:
            business_service, database = await start_business_service()
            event_logger.emit("business_service_started")
        except Exception as error:
            event_logger.emit(
                "business_service_start_failed",
                error_type=type(error).__name__,
            )
            raise

    pipeline = create_voice_pipeline(
        settings or load_voice_pipeline_settings(),
        factories=factories,
    )
    session = create_agent_session(
        pipeline,
        vad_model=get_prewarmed_vad(ctx),
        detector_factory=factories.turn_detector,
    )
    event_logger.bind(session)

    try:
        await session.start(  # pyright: ignore[reportUnknownMemberType]
            room=ctx.room,
            agent=Assistant(business_service, event_logger),
        )
        event_logger.emit("session_started", room_name=ctx.room.name)
        session.say(WELCOME_GREETING, allow_interruptions=True)
    except Exception as error:
        event_logger.emit("session_start_failed", error_type=type(error).__name__)
        await session.aclose()
        await pipeline.aclose(event_logger=event_logger, reason="startup_failure")
        if database is not None:
            await database.close()
        raise

    async def close_pipeline(reason: str) -> None:
        await pipeline.aclose(event_logger=event_logger, reason=reason)
        if database is not None:
            await database.close()
            event_logger.emit("business_service_closed", reason=reason)
        if trace_runtime is not None:
            trace_runtime.flush()
            event_logger.emit("langfuse_traces_flushed", reason=reason)

    ctx.add_shutdown_callback(close_pipeline)
