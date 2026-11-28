"""Speech engines.

All engines share one tiny interface so the rest of the module does not care how
sound is produced:

    speak(text, on_start=None) -> bool   blocking; True = finished, False = interrupted
    interrupt()                          thread-safe; makes the running speak() return False
    clear_interrupt()                    called by the manager before each new message
    shutdown()

Engines:
    Pyttsx3Engine   real offline speech (Windows SAPI5 / macOS / eSpeak)
    ConsoleEngine   prints to the terminal, simulates speaking time (no audio needed)
    FakeEngine      records what would be said; used by the tests
"""
from __future__ import annotations

import abc
import queue
import threading
import time
import warnings
from typing import Any, Callable, Dict, List, Optional, Tuple


class SpeechEngine(abc.ABC):
    def __init__(self) -> None:
        self._interrupt = threading.Event()

    # -- interruption (thread-safe) ------------------------------------------------
    def interrupt(self) -> None:
        self._interrupt.set()

    def clear_interrupt(self) -> None:
        self._interrupt.clear()

    @property
    def interrupted(self) -> bool:
        return self._interrupt.is_set()

    # -- to implement --------------------------------------------------------------
    @abc.abstractmethod
    def speak(self, text: str, on_start: Optional[Callable[[], None]] = None) -> bool:
        """Speak ``text``; block until done. Return False if interrupted."""

    def list_voices(self) -> List[Dict[str, Any]]:
        return []

    def shutdown(self) -> None:
        pass


# ------------------------------------------------------------------------------ fake / console

class FakeEngine(SpeechEngine):
    """No audio. Records everything; optionally simulates speaking time."""

    def __init__(self, duration: float = 0.0, chars_per_second: Optional[float] = None) -> None:
        super().__init__()
        self.duration = duration
        self.chars_per_second = chars_per_second
        self.spoken: List[str] = []              # completed utterances
        self.interrupted_texts: List[str] = []   # utterances cut short
        self.started_at: List[float] = []
        self._fail_with: List[BaseException] = []
        self.shut_down = False

    def fail_next(self, exc: Optional[BaseException] = None, times: int = 1) -> None:
        self._fail_with.extend([exc or RuntimeError("fake engine failure")] * times)

    def _duration_for(self, text: str) -> float:
        if self.chars_per_second:
            return len(text) / self.chars_per_second
        return self.duration

    def speak(self, text: str, on_start: Optional[Callable[[], None]] = None) -> bool:
        if self._fail_with:
            raise self._fail_with.pop(0)
        if self.interrupted:
            self.interrupted_texts.append(text)
            return False
        self.started_at.append(time.monotonic())
        if on_start:
            on_start()
        self._on_speak_begin(text)
        end = time.monotonic() + self._duration_for(text)
        while time.monotonic() < end:
            if self.interrupted:
                self.interrupted_texts.append(text)
                return False
            time.sleep(0.005)
        self.spoken.append(text)
        return True

    def _on_speak_begin(self, text: str) -> None:
        pass

    def shutdown(self) -> None:
        self.shut_down = True


class ConsoleEngine(FakeEngine):
    """Prints speech to the terminal and pretends it takes ~15 characters per second."""

    def __init__(self, chars_per_second: float = 15.0, prefix: str = "[SPEAK] ") -> None:
        super().__init__(chars_per_second=chars_per_second)
        self.prefix = prefix

    def _on_speak_begin(self, text: str) -> None:
        print(f"{self.prefix}{text}", flush=True)


# ------------------------------------------------------------------------------ pyttsx3

_INSTALL_HINT = (
    "pyttsx3 is not installed. Run:  pip install pyttsx3   "
    "(on Windows, if you then see 'No module named win32com', also run: "
    "pip install pywin32 comtypes)"
)


class Pyttsx3Engine(SpeechEngine):
    """Offline speech through pyttsx3.

    pyttsx3 (especially SAPI5 on Windows / COM) must be used from a single thread, and
    its ``runAndWait`` cannot be interrupted cleanly. So this class owns one private
    thread that creates and drives the engine in iterate() mode; every other thread
    only sets flags. That makes ``interrupt()`` safe to call from anywhere.

    rate     words per minute (pyttsx3 default is about 200)
    volume   0.0 - 1.0
    voice    substring of a voice id / name (e.g. "zira", "david", "english")
    recreate_on_interrupt   rebuild the engine after an interruption. Slightly slower
                            (~0.1-0.3 s) but avoids known pyttsx3 'stuck after stop()'
                            problems on some systems.
    """

    def __init__(self, rate: Optional[int] = None, volume: Optional[float] = None,
                 voice: Optional[str] = None, recreate_on_interrupt: bool = True,
                 max_speak_seconds: float = 30.0) -> None:
        super().__init__()
        self.rate = rate
        self.volume = volume
        self.voice = voice
        self.recreate_on_interrupt = recreate_on_interrupt
        self.max_speak_seconds = max_speak_seconds

        self._tasks: "queue.Queue[Optional[Tuple[Callable[[], Any], dict, threading.Event]]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()
        self._engine: Any = None     # only touched from the engine thread

    # -- public ---------------------------------------------------------------------
    def set_rate(self, rate: Optional[int]) -> None:
        self.rate = rate

    def set_volume(self, volume: Optional[float]) -> None:
        self.volume = volume

    def check(self) -> List[Dict[str, Any]]:
        """Create the engine now (so problems show up at start-up) and return voices."""
        return self.list_voices()

    def list_voices(self) -> List[Dict[str, Any]]:
        def job() -> List[Dict[str, Any]]:
            eng = self._get_engine()
            voices = []
            for v in eng.getProperty("voices") or []:
                langs = []
                for lang in getattr(v, "languages", None) or []:
                    langs.append(lang.decode("utf-8", "replace") if isinstance(lang, bytes) else str(lang))
                voices.append({"id": v.id, "name": getattr(v, "name", ""), "languages": langs})
            return voices
        return self._run(job, timeout=30.0)

    def speak(self, text: str, on_start: Optional[Callable[[], None]] = None) -> bool:
        timeout = self.max_speak_seconds + 10.0
        return bool(self._run(lambda: self._speak_in_thread(text, on_start), timeout=timeout))

    def shutdown(self) -> None:
        with self._thread_lock:
            thread = self._thread
            self._thread = None
        if thread is not None and thread.is_alive():
            self._tasks.put(None)
            thread.join(timeout=3.0)

    # -- engine-thread plumbing -----------------------------------------------------
    def _ensure_thread(self) -> None:
        with self._thread_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._worker, name="pyttsx3-engine", daemon=True)
                self._thread.start()

    def _run(self, fn: Callable[[], Any], timeout: float) -> Any:
        self._ensure_thread()
        holder: dict = {}
        done = threading.Event()
        self._tasks.put((fn, holder, done))
        if not done.wait(timeout):
            raise TimeoutError("pyttsx3 engine thread did not respond")
        if "exc" in holder:
            raise holder["exc"]
        return holder.get("val")

    def _worker(self) -> None:
        while True:
            item = self._tasks.get()
            if item is None:
                break
            fn, holder, done = item
            try:
                holder["val"] = fn()
            except BaseException as exc:  # noqa: BLE001 - handed back to the caller
                holder["exc"] = exc
            finally:
                done.set()
        self._teardown_engine()

    # -- everything below runs ONLY on the engine thread ---------------------------
    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            import pyttsx3  # type: ignore
        except ImportError as exc:
            raise ImportError(_INSTALL_HINT) from exc
        eng = pyttsx3.init()
        self._engine = eng
        eng.startLoop(False)
        return eng

    def _apply_properties(self, eng: Any) -> None:
        if self.rate is not None:
            eng.setProperty("rate", int(self.rate))
        if self.volume is not None:
            eng.setProperty("volume", max(0.0, min(1.0, float(self.volume))))
        if self.voice:
            hint = self.voice.lower()
            for v in eng.getProperty("voices") or []:
                if hint in str(v.id).lower() or hint in str(getattr(v, "name", "")).lower():
                    eng.setProperty("voice", v.id)
                    break
            else:
                warnings.warn(f"No installed voice matches {self.voice!r}; using the default voice.")
                self.voice = None  # warn once

    def _teardown_engine(self) -> None:
        eng, self._engine = self._engine, None
        if eng is None:
            return
        try:
            eng.endLoop()
        except Exception:  # noqa: BLE001
            pass

    def _speak_in_thread(self, text: str, on_start: Optional[Callable[[], None]]) -> bool:
        if self.interrupted:
            return False
        eng = self._get_engine()
        self._apply_properties(eng)

        state = {"started": False, "done": False, "error": None}

        def _started(name: Any = None) -> None:
            state["started"] = True
            if on_start:
                try:
                    on_start()
                except Exception:  # noqa: BLE001
                    pass

        def _finished(name: Any = None, completed: bool = True) -> None:
            state["done"] = True

        def _error(name: Any = None, exception: Any = None) -> None:
            state["error"] = exception or RuntimeError("pyttsx3 reported an error")
            state["done"] = True

        tokens = [
            ("started-utterance", eng.connect("started-utterance", _started)),
            ("finished-utterance", eng.connect("finished-utterance", _finished)),
            ("error", eng.connect("error", _error)),
        ]
        interrupted = False
        try:
            eng.say(text)
            deadline = time.monotonic() + self.max_speak_seconds
            while not state["done"]:
                if self.interrupted:
                    eng.stop()
                    interrupted = True
                    break
                if time.monotonic() > deadline:
                    self._teardown_engine()
                    raise TimeoutError(f"pyttsx3 did not finish speaking within {self.max_speak_seconds}s")
                eng.iterate()
                time.sleep(0.01)
                if state["started"] and not state["done"] and not eng.isBusy():
                    state["done"] = True   # some drivers skip the finished event
        finally:
            if self._engine is not None:
                for topic, token in tokens:
                    try:
                        eng.disconnect(token)
                    except Exception:  # noqa: BLE001
                        pass

        if interrupted and self.recreate_on_interrupt:
            self._teardown_engine()
        if state["error"] is not None:
            raise RuntimeError(f"pyttsx3 error: {state['error']}")
        return not interrupted
