"""Member 3 - voice guidance.

Interface:
    VoiceGuidance.speak(decision)   # decision is the dict from obstacle_analyzer
Speech runs on a background thread so the video loop never blocks. Only the
newest pending message is kept, and speech is rate-limited so the system does
not talk continuously.
"""
import queue
import sys
import threading
import time

import config


class PrintBackend:
    """Fallback when pyttsx3 is unavailable (and used in tests)."""

    def __init__(self):
        self.spoken = []

    def say(self, text):
        self.spoken.append(text)
        print(f"[voice] {text}")


class SapiBackend:
    """Windows speech (SAPI) via pywin32. Reliable for repeated speech from a thread."""

    def __init__(self):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()  # COM must be initialised on the speaking thread
        self.voice = win32com.client.Dispatch("SAPI.SpVoice")
        self.voice.Rate = 1  # -10 (slow) .. 10 (fast)

    def say(self, text):
        self.voice.Speak(text)  # blocks until finished


class Pyttsx3Backend:
    """pyttsx3 fallback. Must be created and used on the same thread."""

    def __init__(self, rate=None):
        import pyttsx3
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate or config.SPEECH_RATE)

    def say(self, text):
        self.engine.say(text)
        self.engine.runAndWait()
        self.engine.stop()  # without this, later say() calls can go silent on Windows


class VoiceGuidance:
    def __init__(self, backend_factory=None, min_gap=None):
        self._backend_factory = backend_factory or self._default_backend
        self._min_gap = config.MIN_GAP_BETWEEN_SPEECH_S if min_gap is None else min_gap
        self._queue = queue.Queue(maxsize=1)
        self._enabled = threading.Event()
        self._enabled.set()
        self._running = False
        self._thread = None
        self._last_end = 0.0

    @staticmethod
    def _default_backend():
        if sys.platform.startswith("win"):
            try:
                return SapiBackend()
            except Exception as exc:
                print(f"[voice] SAPI unavailable ({exc}); trying pyttsx3")
        try:
            return Pyttsx3Backend()
        except Exception as exc:  # missing package, no audio device, ...
            print(f"[voice] pyttsx3 unavailable ({exc}); printing instead")
            return PrintBackend()

    # --- control ------------------------------------------------------------
    def start(self):
        if self._thread is None:
            self._running = True
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._running = False
        self._drain()
        self._queue.put(None)  # wake the worker
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def mute(self):
        self._enabled.clear()
        self._drain()

    def unmute(self):
        self._enabled.set()

    @property
    def muted(self):
        return not self._enabled.is_set()

    # --- speaking -----------------------------------------------------------
    def speak(self, decision):
        """Queue a decision (or plain string). A newer message replaces an unspoken older one."""
        if decision is None or self.muted:
            return
        text = decision if isinstance(decision, str) else decision["message"]
        self._drain()
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            pass

    def _drain(self):
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def _worker(self):
        backend = self._backend_factory()
        while self._running:
            text = self._queue.get()
            if text is None or not self._running:
                break
            wait = self._min_gap - (time.monotonic() - self._last_end)
            if wait > 0:
                time.sleep(wait)
            if self.muted:
                continue
            try:
                backend.say(text)
            except Exception as exc:  # keep the thread alive if one utterance fails
                print(f"[voice] speech error: {exc}")
            self._last_end = time.monotonic()


if __name__ == "__main__":
    # Manual test without the rest of the pipeline.
    v = VoiceGuidance().start()
    for msg in ["Person ahead, very close", "Chair on your left", "Car on your right, near"]:
        v.speak(msg)
        time.sleep(3)  # you should hear all three
    v.stop()