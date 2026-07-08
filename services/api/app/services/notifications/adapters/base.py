from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class FailureKind(StrEnum):
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    id: str
    dedupe_key: str
    channel: str
    template: str | None
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SendResult:
    success: bool
    failure_kind: FailureKind | None = None
    message: str | None = None


@runtime_checkable
class ChannelAdapter(Protocol):
    async def send(self, message: OutboxMessage) -> SendResult:
        """Deliver an outbox message on this channel."""


@dataclass
class NoopAdapter:
    """Test adapter that records sends and supports scripted failures."""

    sent: list[OutboxMessage] = field(default_factory=list)
    _sent_dedupe_keys: set[str] = field(default_factory=set)
    failures: dict[str, SendResult] = field(default_factory=dict)

    async def send(self, message: OutboxMessage) -> SendResult:
        scripted = self.failures.get(message.dedupe_key)
        if scripted is not None:
            if scripted.success:
                self._record(message)
            return scripted

        if message.dedupe_key in self._sent_dedupe_keys:
            return SendResult(success=True, message="already_sent")

        self._record(message)
        logger.info(
            "NoopAdapter sent notification",
            extra={"dedupe_key": message.dedupe_key, "channel": message.channel},
        )
        return SendResult(success=True)

    def _record(self, message: OutboxMessage) -> None:
        self._sent_dedupe_keys.add(message.dedupe_key)
        self.sent.append(message)
