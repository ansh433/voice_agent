"""Structured event logging for a LiveKit voice session."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import cast

from livekit.agents import AgentSession, llm
from livekit.agents.voice.events import (
    AgentStateChangedEvent,
    CloseEvent,
    ConversationItemAddedEvent,
    ErrorEvent,
    UserInputTranscribedEvent,
    UserStateChangedEvent,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SessionIdentifiers:
    """Stable identifiers attached to every event in one voice session."""

    session_id: str
    correlation_id: str


class VoiceEventLogger:
    """Bind chronological, correlation-aware structured voice events."""

    def __init__(
        self,
        identifiers: SessionIdentifiers,
        *,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self._identifiers = identifiers
        self._logger = logger

    def emit(self, event: str, **fields: object) -> None:
        """Emit an event without ever serializing provider exceptions or credentials."""
        message = json.dumps(
            {"event": event, **fields},
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        self._logger.info(
            message,
            extra={
                "session_id": self._identifiers.session_id,
                "correlation_id": self._identifiers.correlation_id,
            },
        )

    def bind(self, session: AgentSession[object]) -> None:
        """Subscribe to state, transcript, conversation, error, and close events."""

        def on_user_state(event: UserStateChangedEvent) -> None:
            self.emit(
                "user_state_changed",
                old_state=event.old_state,
                new_state=event.new_state,
            )

        def on_agent_state(event: AgentStateChangedEvent) -> None:
            self.emit(
                "agent_state_changed",
                old_state=event.old_state,
                new_state=event.new_state,
            )

        def on_transcript(event: UserInputTranscribedEvent) -> None:
            self.emit(
                "user_transcript",
                transcript=event.transcript,
                is_final=event.is_final,
                language=str(event.language) if event.language is not None else None,
            )

        def on_conversation_item(event: ConversationItemAddedEvent) -> None:
            item = event.item
            if not isinstance(item, llm.ChatMessage) or item.role not in {"user", "assistant"}:
                return
            self.emit(
                "conversation_item",
                role=item.role,
                text=item.text_content or "",
                interrupted=item.interrupted,
            )

        def on_error(event: ErrorEvent) -> None:
            error = cast(object, event.error)
            source = cast(object, event.source)
            self.emit(
                "session_error",
                error_type=type(error).__name__,
                source_type=type(source).__name__,
            )

        def on_close(event: CloseEvent) -> None:
            self.emit(
                "session_closed",
                reason=event.reason.value,
                error_type=type(event.error).__name__ if event.error is not None else None,
            )

        # LiveKit's EventEmitter callback return is intentionally untyped in 1.8.5.
        session.on("user_state_changed", on_user_state)  # pyright: ignore[reportUnknownMemberType]
        session.on("agent_state_changed", on_agent_state)  # pyright: ignore[reportUnknownMemberType]
        session.on(  # pyright: ignore[reportUnknownMemberType]
            "user_input_transcribed", on_transcript
        )
        session.on(  # pyright: ignore[reportUnknownMemberType]
            "conversation_item_added", on_conversation_item
        )
        session.on("error", on_error)  # pyright: ignore[reportUnknownMemberType]
        session.on("close", on_close)  # pyright: ignore[reportUnknownMemberType]
