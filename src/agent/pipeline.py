"""LiveKit voice-pipeline construction and provider ownership."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol, cast

import httpx2 as httpx
from livekit.agents import (
    AgentSession,
    TurnHandlingOptions,
    inference,
    llm,
    stt,
    tts,
    vad,
)
from livekit.plugins import deepgram, elevenlabs, groq

from configuration import VoicePipelineSettings

from .events import VoiceEventLogger

DEEPGRAM_KEYTERMS = [
    "MotorMitra",
    "service centre",
    "servicing",
    "booking",
    "reschedule",
    "Andheri",
]
LLM_TIMEOUT_SECONDS = 20.0


class STTFactory(Protocol):
    """Construct the configured speech recognizer."""

    def __call__(
        self, *, model: str, language: str, keyterm: list[str], api_key: str
    ) -> stt.STT[object]: ...


class LLMFactory(Protocol):
    """Construct the configured response model."""

    def __call__(
        self,
        *,
        model: str,
        api_key: str,
        timeout: httpx.Timeout,
    ) -> llm.LLM[object]: ...


class TTSFactory(Protocol):
    """Construct the configured speech synthesizer."""

    def __call__(
        self,
        *,
        model: str,
        language: str,
        voice_id: str,
        api_key: str,
        sync_alignment: bool,
    ) -> tts.TTS[object]: ...


class TurnDetectorFactory(Protocol):
    """Construct the audio turn detector."""

    def __call__(self) -> inference.TurnDetector: ...


def _create_deepgram_stt(
    *, model: str, language: str, keyterm: list[str], api_key: str
) -> stt.STT[object]:
    return cast(
        stt.STT[object],
        deepgram.STT(model=model, language=language, keyterm=keyterm, api_key=api_key),
    )


def _create_groq_llm(*, model: str, api_key: str, timeout: httpx.Timeout) -> llm.LLM[object]:
    return cast(
        llm.LLM[object],
        groq.LLM(
            model=model,
            api_key=api_key,
            timeout=timeout,
        ),
    )


def _create_elevenlabs_tts(
    *,
    model: str,
    language: str,
    voice_id: str,
    api_key: str,
    sync_alignment: bool,
) -> tts.TTS[object]:
    return cast(
        tts.TTS[object],
        elevenlabs.TTS(
            model=model,
            language=language,
            voice_id=voice_id,
            api_key=api_key,
            sync_alignment=sync_alignment,
        ),
    )


@dataclass(frozen=True, slots=True)
class ProviderFactories:
    """Injectable provider constructors used by the pipeline factory."""

    stt: STTFactory = _create_deepgram_stt
    llm: LLMFactory = _create_groq_llm
    tts: TTSFactory = _create_elevenlabs_tts
    turn_detector: TurnDetectorFactory = inference.TurnDetector


DEFAULT_PROVIDER_FACTORIES = ProviderFactories()


@dataclass(slots=True)
class VoicePipeline:
    """Owned provider instances for one session."""

    stt: stt.STT[object]
    llm: llm.LLM[object]
    tts: tts.TTS[object]
    _closed: bool = field(default=False, init=False)
    _close_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def aclose(
        self,
        *,
        event_logger: VoiceEventLogger | None = None,
        reason: str = "session_shutdown",
    ) -> None:
        """Close every provider once while allowing the remaining closes to run."""
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True

            results = await asyncio.gather(
                self.stt.aclose(),
                self.llm.aclose(),
                self.tts.aclose(),
                return_exceptions=True,
            )
            for provider, result in zip(("stt", "llm", "tts"), results, strict=True):
                if isinstance(result, BaseException) and event_logger is not None:
                    event_logger.emit(
                        "provider_cleanup_failed",
                        provider=provider,
                        error_type=type(result).__name__,
                    )
            if event_logger is not None:
                event_logger.emit("providers_closed", reason=reason)


def create_voice_pipeline(
    settings: VoicePipelineSettings,
    *,
    factories: ProviderFactories = DEFAULT_PROVIDER_FACTORIES,
) -> VoicePipeline:
    """Create the fixed Stage 1 cascaded provider pipeline without network calls."""
    recognizer = factories.stt(
        model=settings.deepgram_model,
        language=settings.deepgram_language,
        keyterm=list(DEEPGRAM_KEYTERMS),
        api_key=settings.deepgram_api_key.get_secret_value(),
    )
    response_model = factories.llm(
        model=settings.groq_model,
        api_key=settings.groq_api_key.get_secret_value(),
        timeout=httpx.Timeout(LLM_TIMEOUT_SECONDS),
    )
    synthesizer = factories.tts(
        model=settings.eleven_model,
        language=settings.eleven_language,
        voice_id=settings.eleven_voice_id,
        api_key=settings.eleven_api_key.get_secret_value(),
        sync_alignment=True,
    )
    return VoicePipeline(stt=recognizer, llm=response_model, tts=synthesizer)


def create_turn_handling_options(
    *,
    detector_factory: TurnDetectorFactory = inference.TurnDetector,
) -> TurnHandlingOptions:
    """Create the interruptible audio-inference turn configuration."""
    return {
        "turn_detection": detector_factory(),
        "interruption": {"enabled": True},
    }


def create_agent_session(
    pipeline: VoicePipeline,
    *,
    vad_model: vad.VAD,
    detector_factory: TurnDetectorFactory = inference.TurnDetector,
) -> AgentSession[object]:
    """Compose a LiveKit session from prewarmed VAD and owned providers."""
    return AgentSession[object](
        stt=pipeline.stt,
        llm=pipeline.llm,
        tts=pipeline.tts,
        vad=vad_model,
        turn_handling=create_turn_handling_options(detector_factory=detector_factory),
        use_tts_aligned_transcript=True,
    )
