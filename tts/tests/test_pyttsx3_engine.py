"""Tests Pyttsx3Engine's threading/event logic against a mock pyttsx3 (no audio needed).

It does NOT prove your Windows voice works - use `python -m guidesync_tts` for that.
"""
import sys
import threading
import time
import types

import pytest

from guidesync_tts import Pyttsx3Engine, SpeechConfig, SpeechManager


class FakeVoice:
    def __init__(self, vid, name):
        self.id, self.name, self.languages = vid, name, [b"en"]


class FakePyttsx3Engine:
    """Mimics the pyttsx3 external-loop API: say() -> iterate() -> events."""
    instances = []

    def __init__(self, speak_ticks=10):
        self.props = {}
        self.cbs = {}
        self.queue = []
        self.ticks = 0
        self.speak_ticks = speak_ticks
        self.busy = False
        self.thread = threading.current_thread()
        self.spoken = []
        self.stopped = False
        FakePyttsx3Engine.instances.append(self)

    def startLoop(self, useDriverLoop=True): pass
    def endLoop(self): pass

    def connect(self, topic, cb):
        self.cbs[topic] = cb
        return (topic, cb)

    def disconnect(self, token): self.cbs.pop(token[0], None)

    def getProperty(self, name):
        if name == "voices":
            return [FakeVoice("v1", "Microsoft David"), FakeVoice("v2", "Microsoft Zira")]
        return self.props.get(name)

    def setProperty(self, name, value): self.props[name] = value
    def say(self, text): self.queue.append(text)
    def isBusy(self): return self.busy

    def stop(self):
        self.queue.clear(); self.busy = False; self.stopped = True

    def iterate(self):
        assert threading.current_thread() is self.thread, "pyttsx3 used from two threads"
        if self.queue and not self.busy:
            self.current = self.queue.pop(0)
            self.busy, self.ticks = True, 0
            self.cbs["started-utterance"](name=None)
        elif self.busy:
            self.ticks += 1
            if self.ticks >= self.speak_ticks:
                self.busy = False
                self.spoken.append(self.current)
                self.cbs["finished-utterance"](name=None, completed=True)


@pytest.fixture
def mock_pyttsx3(monkeypatch):
    FakePyttsx3Engine.instances.clear()
    mod = types.ModuleType("pyttsx3")
    mod.init = lambda *a, **k: FakePyttsx3Engine()
    monkeypatch.setitem(sys.modules, "pyttsx3", mod)
    return mod


def test_speak_and_properties(mock_pyttsx3):
    eng = Pyttsx3Engine(rate=150, volume=2.0, voice="zira")
    starts = []
    assert eng.speak("hello", on_start=lambda: starts.append(1)) is True
    inst = FakePyttsx3Engine.instances[-1]
    assert inst.spoken == ["hello"] and starts == [1]
    assert inst.props["rate"] == 150 and inst.props["volume"] == 1.0 and inst.props["voice"] == "v2"
    eng.shutdown()


def test_list_voices(mock_pyttsx3):
    eng = Pyttsx3Engine()
    assert [v["name"] for v in eng.list_voices()] == ["Microsoft David", "Microsoft Zira"]
    eng.shutdown()


def test_interrupt_from_other_thread(mock_pyttsx3):
    eng = Pyttsx3Engine()
    threading.Timer(0.05, eng.interrupt).start()
    mock_pyttsx3.init = lambda *a, **k: FakePyttsx3Engine(speak_ticks=10_000)
    eng._teardown_engine = lambda: None  # keep the first instance irrelevant
    t0 = time.monotonic()
    assert eng.speak("a very long sentence") is False
    assert time.monotonic() - t0 < 2
    eng.shutdown()


def test_works_through_manager_and_recreates_after_interrupt(mock_pyttsx3):
    eng = Pyttsx3Engine()
    m = SpeechManager(eng, SpeechConfig())
    with m:
        m.say("one"); m.wait_until_idle(3)
        m.say("two"); m.wait_until_idle(3)
    spoken = [s for i in FakePyttsx3Engine.instances for s in i.spoken]
    assert spoken == ["one", "two"]


def test_missing_library_gives_helpful_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyttsx3", None)   # makes `import pyttsx3` raise ImportError
    eng = Pyttsx3Engine()
    with pytest.raises(ImportError, match="pip install pyttsx3"):
        eng.speak("x")
    eng.shutdown()
