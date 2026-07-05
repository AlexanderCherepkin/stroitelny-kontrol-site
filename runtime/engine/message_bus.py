from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..contracts.message import DeliveryGuarantee, DeliveryReceipt, Message, MessageStatus, MessageType


@dataclass
class Subscriber:
    id: str
    callback: Callable[[Message], Awaitable[None]]
    topics: list[str]
    qos: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 3
    healthy: bool = True
    consecutive_failures: int = 0


@dataclass
class DeadLetterEntry:
    message: Message
    failure_reason: str
    timestamp: float = field(default_factory=time.time)


class MessageBus:
    MAX_QUEUE_DEPTH = 10_000
    CIRCUIT_BREAKER_THRESHOLD = 3
    CIRCUIT_BREAKER_COOLDOWN = 60

    def __init__(self):
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)
        self._dead_letter: list[DeadLetterEntry] = []
        self._delivery_log: list[DeliveryReceipt] = []
        self._processing_tasks: set[asyncio.Task[Any]] = set()
        self._running = False
        self._dedup_store: set[str] = set()

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    def subscribe(self, subscriber_id: str, callback: Callable[[Message], Awaitable[None]], topics: list[str],
                  max_retries: int = 3):
        sub = Subscriber(id=subscriber_id, callback=callback, topics=list(topics), max_retries=max_retries)
        for topic in topics:
            self._subscribers[topic].append(sub)

    def unsubscribe(self, subscriber_id: str):
        for topic, subs in self._subscribers.items():
            self._subscribers[topic] = [s for s in subs if s.id != subscriber_id]

    async def publish(self, message: Message) -> DeliveryReceipt:
        if message.delivery_guarantee == DeliveryGuarantee.EXACTLY_ONCE:
            if message.message_id in self._dedup_store:
                return DeliveryReceipt(
                    message_id=message.message_id,
                    recipient="system",
                    status=MessageStatus.REJECTED,
                    failure_reason="Duplicate message (exactly-once)",
                )
            self._dedup_store.add(message.message_id)

        topic_subs = self._subscribers.get(message.topic, [])
        if not topic_subs:
            self._dead_letter.append(DeadLetterEntry(
                message=message,
                failure_reason=f"No subscribers for topic '{message.topic}'",
            ))
            return DeliveryReceipt(
                message_id=message.message_id,
                recipient="none",
                status=MessageStatus.DEAD_LETTERED,
                failure_reason=f"No subscribers for topic '{message.topic}'",
            )

        healthy_subs = [s for s in topic_subs if s.healthy]
        if not healthy_subs:
            self._dead_letter.append(DeadLetterEntry(
                message=message,
                failure_reason="All subscribers unhealthy",
            ))
            return DeliveryReceipt(
                message_id=message.message_id,
                recipient="all",
                status=MessageStatus.DEAD_LETTERED,
                failure_reason="All subscribers unhealthy",
            )

        receipts: list[DeliveryReceipt] = []
        for sub in healthy_subs:
            if message.recipient_filter and message.recipient_filter != sub.id:
                continue
            receipts.append(await self._deliver_to(sub, message))

        return self._merge_receipts(receipts)

    async def _deliver_to(self, subscriber: Subscriber, message: Message, attempt: int = 1) -> DeliveryReceipt:
        try:
            await asyncio.wait_for(subscriber.callback(message), timeout=30)
            subscriber.consecutive_failures = 0
            subscriber.healthy = True
            return DeliveryReceipt(message_id=message.message_id, recipient=subscriber.id, status=MessageStatus.DELIVERED)
        except asyncio.TimeoutError:
            return await self._handle_delivery_failure(subscriber, message, "Timeout", attempt)
        except Exception as e:
            return await self._handle_delivery_failure(subscriber, message, str(e), attempt)

    async def _handle_delivery_failure(self, subscriber: Subscriber, message: Message, reason: str,
                                       attempt: int) -> DeliveryReceipt:
        subscriber.consecutive_failures += 1

        if subscriber.consecutive_failures >= self.CIRCUIT_BREAKER_THRESHOLD:
            subscriber.healthy = False
            return DeliveryReceipt(
                message_id=message.message_id, recipient=subscriber.id,
                status=MessageStatus.DEAD_LETTERED,
                failure_reason=f"Circuit breaker open after {subscriber.consecutive_failures} failures",
            )

        if attempt < subscriber.max_retries and message.delivery_guarantee != DeliveryGuarantee.AT_MOST_ONCE:
            await asyncio.sleep(2 ** attempt * 0.1)
            return await self._deliver_to(subscriber, message, attempt + 1)

        return DeliveryReceipt(
            message_id=message.message_id, recipient=subscriber.id,
            status=MessageStatus.FAILED, failure_reason=reason,
        )

    def _merge_receipts(self, receipts: list[DeliveryReceipt]) -> DeliveryReceipt:
        if not receipts:
            return DeliveryReceipt(message_id="", recipient="none", status=MessageStatus.FAILED)
        if all(r.status == MessageStatus.DELIVERED for r in receipts):
            return DeliveryReceipt(message_id=receipts[0].message_id, recipient="all", status=MessageStatus.DELIVERED)
        if any(r.status == MessageStatus.DELIVERED for r in receipts):
            return DeliveryReceipt(message_id=receipts[0].message_id, recipient="partial", status=MessageStatus.DELIVERED)
        return receipts[0]
