"""Module 3 - voice guidance facade over ``modules.tts``.

Provides ``VoiceGuidance`` backed by ``SpeechManager`` (priority queue,
cooldown suppression, object staleness filtering, repeat/summary requests, and
interruptible pyttsx3 speech).
"""
from __future__ import annotations

import time
from typing import Any, Callable

import config
from modules.tts import (
    KIND_OBJECT,
    ConsoleEngine,
    Pyttsx3Engine,
    SpeechConfig,
    SpeechEngine,
    SpeechManager,
)


class PrintBackend:
    """Fallback backend that prints spoken text (also used by --no-voice and tests)."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def say(self, text: str) -> None:
        self.spoken.append(text)
        print(f"[voice] {text}")


class _BackendEngine(SpeechEngine):
    """Adapt a simple ``say(text)`` backend factory to ``SpeechEngine``."""

    def __init__(self, backend_factory: Callable[[], Any], min_gap: float = 0.0) -> None:
        super().__init__()
        self._backend_factory = backend_factory
        self._backend: Any = None
        self._min_gap = min_gap
        self._last_end = 0.0

    def speak(self, text: str, on_start: Callable[[], None] | None = None) -> bool:
        if self.interrupted:
            return False
        if self._backend is None:
            self._backend = self._backend_factory()
        wait = self._min_gap - (time.monotonic() - self._last_end)
        if wait > 0:
            end = time.monotonic() + wait
            while time.monotonic() < end:
                if self.interrupted:
                    return False
                time.sleep(0.01)
        if on_start:
            on_start()
        self._backend.say(text)
        self._last_end = time.monotonic()
        return not self.interrupted


class VoiceGuidance:
    """Thread-safe voice output controller integrating ``SpeechManager``."""

    def __init__(
        self,
        backend_factory: Callable[[], Any] | None = None,
        min_gap: float | None = None,
        speech_config: SpeechConfig | None = None,
    ) -> None:
        self._backend_factory = backend_factory
        self._min_gap = config.MIN_GAP_BETWEEN_SPEECH_S if min_gap is None else min_gap
        if speech_config is None:
            speech_config = SpeechConfig(cooldown_s=config.REPEAT_COOLDOWN_S)
            speech_config.ttl_by_kind[KIND_OBJECT] = config.TTS_OBJECT_TTL_S
        self._speech_config = speech_config
        self._manager: SpeechManager | None = None
        self._muted = False

    def _build_engine(self) -> SpeechEngine:
        if self._backend_factory is not None:
            return _BackendEngine(self._backend_factory, self._min_gap)
        try:
            eng = Pyttsx3Engine(rate=config.SPEECH_RATE, voice=config.SPEECH_VOICE)
            eng.check()
            return eng
        except Exception as exc:  # missing package, no audio device, ...
            print(f"[voice] pyttsx3 unavailable ({exc}); printing instead")
            return ConsoleEngine()

    @property
    def manager(self) -> SpeechManager:
        """Return the active ``SpeechManager``, starting it lazily if needed."""
        if self._manager is None:
            self.start()
        assert self._manager is not None
        return self._manager

    # --- lifecycle ----------------------------------------------------------
    def start(self) -> "VoiceGuidance":
        if self._manager is None:
            self._manager = SpeechManager(self._build_engine(), self._speech_config)
            if self._muted:
                self._manager.pause()
        return self

    def stop(self) -> None:
        if self._manager is not None:
            self._manager.close()
            self._manager = None

    def __enter__(self) -> "VoiceGuidance":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    # --- controls -----------------------------------------------------------
    def mute(self) -> None:
        self._muted = True
        if self._manager is not None:
            self._manager.pause()

    def unmute(self) -> None:
        self._muted = False
        if self._manager is not None:
            self._manager.resume()

    @property
    def muted(self) -> bool:
        return self._manager.paused if self._manager is not None else self._muted

    # --- speaking -----------------------------------------------------------
    def speak(self, decision: Any, **kwargs: Any) -> None:
        """Submit text, obstacle decisions, checkpoint events, or system notices."""
        if decision is None or self.muted:
            return
        self.manager.submit(decision, **kwargs)

    def repeat(self) -> None:
        """Repeat the last spoken message."""
        self.manager.repeat_last()

    def summary(self) -> None:
        """Speak a brief summary of recently seen objects."""
        self.manager.request_summary()

    def cancel_objects(self, reason: str = "camera_lost") -> int:
        """Drop queued object announcements (e.g. on camera loss)."""
        if self._manager is None:
            return 0
        return self._manager.cancel_pending([KIND_OBJECT], interrupt_current=False, reason=reason)

    def stats(self) -> dict[str, Any]:
        """Return SpeechManager statistics."""
        return self.manager.stats()

    def export_log(self, path: str) -> None:
        """Export SpeechManager event logs to CSV or JSON."""
        self.manager.export_log(path)


if __name__ == "__main__":
    with VoiceGuidance() as voice:
        for msg in ["Person ahead, very close", "Chair on your left", "Car on your right, near"]:
            voice.speak(msg)
            time.sleep(3)
