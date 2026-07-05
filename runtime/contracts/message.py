from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    COMMAND = "command"
    EVENT = "event"
    QUERY = "query"
    REPLY = "reply"
    BROADCAST = "broadcast"


class DeliveryGuarantee(str, Enum):
    AT_MOST_ONCE = "at_most_once"
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"


class MessageStatus(str, Enum):
    DELIVERED = "delivered"
    QUEUED = "queued"
    REJECTED = "rejected"
    DEAD_LETTERED = "dead_lettered"
    FAILED = "failed"


class Topic(str, Enum):
    SAFETY_PRE_CHECK = "safety.pre_check"
    SAFETY_POST_CHECK = "safety.post_check"
    EXECUTION_RESULT = "execution.result"
    EXECUTION_COMMAND = "execution.command"
    SYSTEM_ALERT = "system.alert"
    CONTROL_SIGNAL = "control.signal"
    MUTUAL_VALIDATION = "mutual.validation"
    OBSERVATION = "observation"
    PLANNING = "planning"
    RESULT = "result"
    AUDIT = "audit"


@dataclass
class Message:
    payload: Any
    message_type: MessageType
    topic: str
    delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_LEAST_ONCE
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    correlation_id: str | None = None
    sender: str | None = None
    recipient_filter: str | None = None
    timestamp: float = field(default_factory=time.time)
    hop_count: int = 0
    max_hops: int = 10

    def bump_hop(self) -> bool:
        self.hop_count += 1
        return self.hop_count <= self.max_hops


@dataclass
class DeliveryReceipt:
    message_id: str
    recipient: str
    status: MessageStatus
    timestamp: float = field(default_factory=time.time)
    failure_reason: str | None = None
