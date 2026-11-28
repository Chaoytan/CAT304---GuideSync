"""Internal message type shared by every part of the TTS module.

Whatever the upstream modules send (strings, dicts, detections, marker events...),
adapters turn it into one or more ``Message`` objects, and the SpeechManager only
ever deals with ``Message``.
"""
from __future__ import annotations

import enum
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class Priority(enum.IntEnum):
    """Higher number = more important."""

    LOW = 1
    NORMAL = 2          # routine object announcements, plain text
    HIGH = 3            # checkpoint / route information
    USER_REQUEST = 4    # repeat / summary requested by the user
    CRITICAL = 5        # system failures (camera lost, detector crashed...)

    @classmethod
    def parse(cls, value: Any, default: Optional["Priority"] = None) -> "Priority":
        if isinstance(value, cls):
            return value
        if isinstance(value, bool):
            raise ValueError(f"Invalid priority: {value!r}")
        if isinstance(value, int):
            try:
                return cls(value)
            except ValueError:
                raise ValueError(f"Priority number must be 1-5, got {value}") from None
        if isinstance(value, str):
            name = value.strip().upper().replace(" ", "_").replace("-", "_")
            aliases = {
                "USER": "USER_REQUEST",
                "REQUEST": "USER_REQUEST",
                "URGENT": "CRITICAL",
                "ERROR": "CRITICAL",
                "ROUTINE": "NORMAL",
                "MEDIUM": "NORMAL",
                "INFO": "LOW",
            }
            name = aliases.get(name, name)
            if name in cls.__members__:
                return cls[name]
        if default is not None:
            return default
        raise ValueError(f"Invalid priority: {value!r}")


# Message kinds. Free-form strings are allowed; these are the ones the module knows.
KIND_TEXT = "text"
KIND_OBJECT = "object"
KIND_ROUTE = "route"
KIND_SYSTEM = "system"
KIND_USER = "user"

NEVER_EXPIRES = math.inf


def normalise_text(text: str) -> str:
    """Lower-case, strip punctuation and collapse spaces (used for default keys)."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


@dataclass(eq=False)
class Message:
    """One thing to say.

    text             what to speak
    priority         see Priority
    key              duplicate key; messages with the same key are "the same message"
                     for cooldown and queue de-duplication. Default: kind + normalised text.
    kind             "object", "route", "system", "user", "text" or anything you like
    ttl              seconds the message stays valid, counted from ``created_at``.
                     None -> use the manager's default for this kind.
                     float("inf") -> never expires.
    created_at       time.monotonic() timestamp of the source event (e.g. the camera
                     frame). None -> stamped by the manager at submit time.
    interrupt        if True, interrupts the message currently being spoken
                     (unless that one is more important).
    bypass_cooldown  if True, ignores the repeat cooldown (used for user requests).
    meta             free-form extras (label, confidence, position...), logged only.
    """

    text: str
    priority: Priority = Priority.NORMAL
    key: Optional[str] = None
    kind: str = KIND_TEXT
    ttl: Optional[float] = None
    created_at: Optional[float] = None
    interrupt: bool = False
    bypass_cooldown: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)
    seq: int = -1  # assigned by the manager

    @property
    def effective_key(self) -> str:
        return self.key or f"{self.kind}:{normalise_text(self.text)}"
