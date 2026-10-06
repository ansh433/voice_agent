"""LiveKit worker composition root for the MotorMitra voice agent."""

import os
from collections.abc import Callable

from dotenv import load_dotenv
from livekit.agents import AgentServer, JobContext, JobProcess, cli, vad
from livekit.plugins import silero

from observability.logging import configure_logging

from .session import PREWARMED_VAD_KEY, run_voice_session

# LiveKit's worker reads its connection credentials and agent name directly from
# os.environ. Populate it before AgentServer and @rtc_session are constructed.
load_dotenv()


def prewarm_process(
    proc: JobProcess,
    *,
    vad_loader: Callable[[], vad.VAD] = silero.VAD.load,
) -> None:
    """Load Silero once per worker process for reuse by each job."""
    proc.userdata[PREWARMED_VAD_KEY] = vad_loader()


server = AgentServer(setup_fnc=prewarm_process)


@server.rtc_session()
async def motor_mitra_session(ctx: JobContext) -> None:
    """Run one browser voice session."""
    await run_voice_session(ctx)


def main() -> None:
    """Run the LiveKit worker CLI."""
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    cli.run_app(server)


if __name__ == "__main__":
    main()
