"""SpeechManager: decides WHAT is spoken and WHEN, then hands text to a SpeechEngine.

Implements the proposal's speech rules (section 5.2):
  * priority + age + duplicate-key message selection
  * repeat suppression (default 5 s cooldown per key)
  * stale-message rejection (default 2 s validity for object messages), re-checked
    immediately before playback
  * pause / shutdown / system failures interrupt routine speech
  * explicit user requests (repeat, summary) beat routine messages
  * small bounded queue
  * event log with latency, so the evaluation measures in 5.4 can be produced
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

from .adapters import AdapterOptions, normalize
from .engine import SpeechEngine
from .message import (
    KIND_OBJECT,
    KIND_ROUTE,
    KIND_SYSTEM,
    KIND_TEXT,
    KIND_USER,
    NEVER_EXPIRES,
    Message,
    Priority,
)


@dataclass
class SpeechConfig:
    cooldown_s: float = 5.0                      # same key not repeated inside this window
    max_queue: int = 5                           # bounded pending set
    suppression: bool = True                     # False = "baseline": speak every detection
    default_ttl_s: float = 10.0
    ttl_by_kind: Dict[str, float] = field(default_factory=lambda: {
        KIND_OBJECT: 2.0,                        # proposal: 2 s validity for object messages
        KIND_ROUTE: 6.0,
        KIND_SYSTEM: NEVER_EXPIRES,
        KIND_USER: 15.0,
        KIND_TEXT: 10.0,
    })
    pause_allows: Priority = Priority.USER_REQUEST   # while paused, only >= this is spoken
    critical_interrupts: bool = True             # CRITICAL always cuts off lower-priority speech
    summary_window_s: float = 3.0                # how far back "summary" looks
    summary_empty_text: str = "Nothing detected."
    repeat_empty_text: str = "Nothing to repeat."
    log_size: int = 20000
    adapter_options: AdapterOptions = field(default_factory=AdapterOptions)

    def ttl_for(self, msg: Message) -> float:
        if msg.ttl is not None:
            return msg.ttl
        return self.ttl_by_kind.get(msg.kind, self.default_ttl_s)


@dataclass
class SubmitResult:
    message: Message
    accepted: bool
    reason: str          # queued | replaced | cooldown | empty | paused | duplicate_active |
                         # queue_full | expired | closed


class SpeechManager:
    def __init__(self, engine: SpeechEngine, config: Optional[SpeechConfig] = None,
                 on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
                 clock: Callable[[], float] = time.monotonic,
                 autostart: bool = True) -> None:
        self.engine = engine
        self.config = config or SpeechConfig()
        self.on_event = on_event
        self.clock = clock

        self._cond = threading.Condition()
        self._pending: List[Message] = []
        self._current: Optional[Message] = None
        self._current_start: Optional[float] = None
        self._last_spoken_end: Dict[str, float] = {}
        self._last_spoken_msg: Optional[Message] = None
        self._scene: Dict[str, Message] = {}
        self._scene_time: Dict[str, float] = {}
        self._paused = False
        self._closed = False
        self._seq = 0
        self._log: Deque[Dict[str, Any]] = deque(maxlen=self.config.log_size)
        self.engine_failures = 0
        self._thread = threading.Thread(target=self._run, name="speech-manager", daemon=True)
        self._started = False
        if autostart:
            self.start()

    # ================================================================== lifecycle
    def start(self) -> None:
        if not self._started:
            self._started = True
            self._thread.start()

    def close(self, drain: bool = False, timeout: float = 5.0) -> None:
        """Stop the worker. drain=True lets pending messages finish first."""
        if drain:
            self.wait_until_idle(timeout)
        with self._cond:
            self._closed = True
            self._drop_all_locked("shutdown")
            if self._current is not None:
                self.engine.interrupt()
            self._cond.notify_all()
        if self._started:
            self._thread.join(timeout)
        self.engine.shutdown()

    def __enter__(self) -> "SpeechManager":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ================================================================== input
    def submit(self, raw: Any, *, priority: Any = None, key: Optional[str] = None,
               ttl: Optional[float] = None, interrupt: Optional[bool] = None,
               kind: Optional[str] = None,
               created_at: Optional[float] = None) -> List[SubmitResult]:
        """Offer ANY supported input (str, dict, detection, list...). Non-blocking.

        Keyword arguments, if given, override the fields of every resulting message.
        Raises UnsupportedInputError for input nothing understands.
        """
        messages = normalize(raw, self.config.adapter_options)
        results: List[SubmitResult] = []
        for msg in messages:
            if priority is not None:
                msg.priority = Priority.parse(priority)
            if key is not None:
                msg.key = key
            if ttl is not None:
                msg.ttl = ttl
            if interrupt is not None:
                msg.interrupt = interrupt
            if kind is not None:
                msg.kind = kind
            if created_at is not None:
                msg.created_at = created_at
            results.append(self._submit_message(msg))
        return results

    def say(self, text: str, **kwargs: Any) -> List[SubmitResult]:
        """Shortcut: ``manager.say("Hello", priority="HIGH")``."""
        return self.submit(text, **kwargs)

    def _submit_message(self, msg: Message) -> SubmitResult:
        now = self.clock()
        cfg = self.config
        with self._cond:
            msg.seq = self._seq
            self._seq += 1
            if msg.created_at is None:
                msg.created_at = now
            msg.text = (msg.text or "").strip()
            key = msg.effective_key

            if msg.kind == KIND_OBJECT:               # remember scene for "summary"
                self._scene[key] = msg
                self._scene_time[key] = now

            if self._closed:
                return self._reject(msg, "closed")
            if not msg.text:
                return self._reject(msg, "empty")
            if now - msg.created_at > cfg.ttl_for(msg):
                return self._reject(msg, "expired")
            if self._paused and msg.priority < cfg.pause_allows:
                return self._reject(msg, "paused")

            self._log_event("submitted", msg)

            if cfg.suppression and not msg.bypass_cooldown:
                last = self._last_spoken_end.get(key)
                if last is not None and now - last < cfg.cooldown_s:
                    return self._reject(msg, "cooldown", log_submit=False)
                if self._current is not None and self._current.effective_key == key:
                    return self._reject(msg, "duplicate_active", log_submit=False)

            reason = "queued"
            if cfg.suppression:
                for i, old in enumerate(self._pending):
                    if old.effective_key == key and not old.bypass_cooldown and not msg.bypass_cooldown:
                        # same message already waiting: keep the newer one, the higher priority
                        msg.priority = max(msg.priority, old.priority)
                        self._pending[i] = msg
                        self._log_event("dropped", old, reason="replaced")
                        reason = "replaced"
                        break
                else:
                    pass
            if reason == "queued":
                self._pending.append(msg)
                if len(self._pending) > cfg.max_queue:
                    victim = min(self._pending, key=lambda m: (m.priority, -m.seq))
                    self._pending.remove(victim)
                    self._log_event("dropped", victim, reason="queue_full")
                    if victim is msg:
                        return SubmitResult(msg, False, "queue_full")

            self._maybe_interrupt_current(msg)
            self._cond.notify_all()
            return SubmitResult(msg, True, reason)

    def _reject(self, msg: Message, reason: str, log_submit: bool = True) -> SubmitResult:
        if log_submit:
            self._log_event("submitted", msg)
        self._log_event("dropped", msg, reason=reason)
        return SubmitResult(msg, False, reason)

    def _maybe_interrupt_current(self, new: Message) -> None:
        cur = self._current
        if cur is None:
            return
        wants = new.interrupt or (self.config.critical_interrupts and new.priority >= Priority.CRITICAL)
        if wants and new.priority >= cur.priority and new.priority > Priority.LOW - 1:
            if cur.priority < Priority.CRITICAL or new.priority >= Priority.CRITICAL:
                self.engine.interrupt()

    # ================================================================== user controls
    def pause(self) -> None:
        """Silence routine speech now and refuse new routine messages until resume()."""
        with self._cond:
            self._paused = True
            keep = []
            for m in self._pending:
                if m.priority >= self.config.pause_allows:
                    keep.append(m)
                else:
                    self._log_event("dropped", m, reason="paused")
            self._pending = keep
            if self._current is not None and self._current.priority < self.config.pause_allows:
                self.engine.interrupt()
            self._log_event("control", None, reason="pause")
            self._cond.notify_all()

    def resume(self) -> None:
        with self._cond:
            self._paused = False
            self._log_event("control", None, reason="resume")
            self._cond.notify_all()

    def toggle_pause(self) -> bool:
        """Start/pause control. Returns True if now paused."""
        if self.paused:
            self.resume()
        else:
            self.pause()
        return self.paused

    @property
    def paused(self) -> bool:
        return self._paused

    def repeat_last(self) -> SubmitResult:
        """User asks 'say that again'."""
        with self._cond:
            last = self._last_spoken_msg
        if last is None:
            text, extra = self.config.repeat_empty_text, "user:repeat_empty"
        else:
            text, extra = last.text, "user:repeat"
        msg = Message(text=text, priority=Priority.USER_REQUEST, key=extra, kind=KIND_USER,
                      bypass_cooldown=True, meta={"user_request": "repeat"})
        return self._submit_message(msg)

    def request_summary(self) -> SubmitResult:
        """User asks 'what do you see?'. Summarises recent object messages."""
        now = self.clock()
        with self._cond:
            recent = [m for k, m in self._scene.items()
                      if now - self._scene_time.get(k, -math.inf) <= self.config.summary_window_s]
        recent.sort(key=lambda m: m.seq)
        if recent:
            text = " ".join(m.text.rstrip(".") + "." for m in recent)
        else:
            text = self.config.summary_empty_text
        msg = Message(text=text, priority=Priority.USER_REQUEST, key="user:summary", kind=KIND_USER,
                      bypass_cooldown=True, meta={"user_request": "summary"})
        return self._submit_message(msg)

    def cancel_pending(self, kinds: Optional[List[str]] = None, interrupt_current: bool = True,
                       reason: str = "cancelled") -> int:
        """Throw away queued (and optionally currently spoken) messages.

        Call this when a source dies, e.g. ``cancel_pending(["object"])`` when the camera is lost,
        so stale object announcements are never read out.
        """
        n = 0
        with self._cond:
            keep = []
            for m in self._pending:
                if kinds is None or m.kind in kinds:
                    self._log_event("dropped", m, reason=reason)
                    n += 1
                else:
                    keep.append(m)
            self._pending = keep
            cur = self._current
            if interrupt_current and cur is not None and (kinds is None or cur.kind in kinds):
                self.engine.interrupt()
            if kinds is None or KIND_OBJECT in kinds:
                self._scene.clear()
                self._scene_time.clear()
            self._cond.notify_all()
        return n

    def clear_cooldowns(self) -> None:
        with self._cond:
            self._last_spoken_end.clear()

    # ================================================================== introspection
    @property
    def pending_count(self) -> int:
        with self._cond:
            return len(self._pending)

    def is_idle(self) -> bool:
        with self._cond:
            return self._current is None and not self._pending

    def wait_until_idle(self, timeout: float = 10.0) -> bool:
        end = time.monotonic() + timeout
        with self._cond:
            while self._current is not None or self._pending:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(min(remaining, 0.05))
        return True

    def get_log(self) -> List[Dict[str, Any]]:
        with self._cond:
            return list(self._log)

    def spoken_log(self) -> List[Dict[str, Any]]:
        return [e for e in self.get_log() if e["event"] == "spoken"]

    def stats(self) -> Dict[str, Any]:
        """Counts, drop reasons and onset-latency percentiles (successful events only)."""
        log = self.get_log()
        drops = Counter(e["reason"] for e in log if e["event"] == "dropped")
        spoken = [e for e in log if e["event"] == "spoken"]
        lat = sorted(e["latency_s"] for e in spoken if e.get("latency_s") is not None)

        def pct(p: float) -> Optional[float]:
            if not lat:
                return None
            idx = max(0, min(len(lat) - 1, math.ceil(p / 100 * len(lat)) - 1))
            return lat[idx]

        return {
            "submitted": sum(1 for e in log if e["event"] == "submitted"),
            "spoken": len(spoken),
            "interrupted": sum(1 for e in log if e["event"] == "interrupted"),
            "dropped": dict(drops),
            "engine_failures": self.engine_failures,
            "latency_median_s": statistics.median(lat) if lat else None,
            "latency_p95_s": pct(95),
            "latency_max_s": lat[-1] if lat else None,
        }

    def export_log(self, path: str) -> None:
        """Write the event log as .csv or .json (decided by extension)."""
        log = self.get_log()
        if path.lower().endswith(".json"):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, default=str)
            return
        cols = ["t", "event", "reason", "kind", "priority", "key", "text", "latency_s", "created_at"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(log)

    # ================================================================== worker
    def _log_event(self, event: str, msg: Optional[Message], **extra: Any) -> None:
        entry: Dict[str, Any] = {"t": self.clock(), "event": event, "reason": extra.pop("reason", "")}
        if msg is not None:
            entry.update(text=msg.text, key=msg.effective_key, kind=msg.kind,
                         priority=msg.priority.name, created_at=msg.created_at)
        entry.update(extra)
        self._log.append(entry)
        if self.on_event is not None:
            try:
                self.on_event(entry)
            except Exception:  # noqa: BLE001 - a bad callback must never stop speech
                pass

    def _drop_all_locked(self, reason: str) -> None:
        for m in self._pending:
            self._log_event("dropped", m, reason=reason)
        self._pending = []

    def _purge_expired_locked(self, now: float) -> None:
        keep = []
        for m in self._pending:
            if now - (m.created_at or now) > self.config.ttl_for(m):
                self._log_event("dropped", m, reason="expired")
            else:
                keep.append(m)
        self._pending = keep

    def _pick_locked(self, now: float) -> Optional[Message]:
        self._purge_expired_locked(now)
        while self._pending:
            cands = [m for m in self._pending
                     if not self._paused or m.priority >= self.config.pause_allows]
            if not cands:
                return None
            best = max(cands, key=lambda m: (m.priority, -m.seq))   # highest priority, then oldest
            self._pending.remove(best)
            if self.config.suppression and not best.bypass_cooldown:
                last = self._last_spoken_end.get(best.effective_key)
                if last is not None and now - last < self.config.cooldown_s:
                    self._log_event("dropped", best, reason="cooldown")
                    continue
            return best
        return None

    def _run(self) -> None:
        while True:
            with self._cond:
                msg = None
                while not self._closed:
                    msg = self._pick_locked(self.clock())
                    if msg is not None:
                        break
                    self._cond.notify_all()          # tell wait_until_idle we are idle
                    self._cond.wait(0.05)            # timeout also drives expiry
                if self._closed:
                    self._cond.notify_all()
                    return
                self._current = msg
                self._current_start = None
                self.engine.clear_interrupt()

            onset: Dict[str, float] = {}

            def _on_start() -> None:
                onset["t"] = self.clock()

            outcome, error = "failed", None
            try:
                finished = self.engine.speak(msg.text, on_start=_on_start)
                outcome = "spoken" if finished else "interrupted"
            except Exception as exc:  # noqa: BLE001
                error = exc
            with self._cond:
                end = self.clock()
                self._current = None
                if outcome == "spoken":
                    self._last_spoken_end[msg.effective_key] = end
                    self._last_spoken_msg = msg
                    onset_t = onset.get("t", end)
                    self._log_event("spoken", msg, onset=onset_t, end=end,
                                    latency_s=onset_t - (msg.created_at or onset_t))
                    self.engine_failures = 0
                elif outcome == "interrupted":
                    self._log_event("interrupted", msg, reason="interrupted")
                else:
                    self.engine_failures += 1
                    self._log_event("engine_error", msg, reason=repr(error))
                self._cond.notify_all()
            if outcome == "failed":
                time.sleep(0.2)   # avoid a hot loop if the audio device is broken
