"""Tests Pyttsx3Engine's threading/event logic against a mock pyttsx3 (no audio needed)."""
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from modules.tts import Pyttsx3Engine, SpeechConfig, SpeechManager


class FakeVoice:
    def __init__(self, vid, name):
        self.id = vid
        self.name = name
        self.languages = [b"en"]


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
        self.current = None
        FakePyttsx3Engine.instances.append(self)

    def startLoop(self, useDriverLoop=True):
        pass

    def endLoop(self):
        pass

    def connect(self, topic, cb):
        self.cbs[topic] = cb
        return (topic, cb)

    def disconnect(self, token):
        self.cbs.pop(token[0], None)

    def getProperty(self, name):
        if name == "voices":
            return [FakeVoice("v1", "Microsoft David"), FakeVoice("v2", "Microsoft Zira")]
        return self.props.get(name)

    def setProperty(self, name, value):
        self.props[name] = value

    def say(self, text):
        self.queue.append(text)

    def isBusy(self):
        return self.busy

    def stop(self):
        self.queue.clear()
        self.busy = False
        self.stopped = True

    def iterate(self):
        assert threading.current_thread() is self.thread, "pyttsx3 used from two threads"
        if self.queue and not self.busy:
            self.current = self.queue.pop(0)
            self.busy = True
            self.ticks = 0
            self.cbs["started-utterance"](name=None)
        elif self.busy:
            self.ticks += 1
            if self.ticks >= self.speak_ticks:
                self.busy = False
                self.spoken.append(self.current)
                self.cbs["finished-utterance"](name=None, completed=True)


class TestPyttsx3Engine(unittest.TestCase):
    def setUp(self):
        FakePyttsx3Engine.instances.clear()
        self.fake_mod = types.ModuleType("pyttsx3")
        self.fake_mod.init = lambda *a, **k: FakePyttsx3Engine()

    def test_speak_and_properties(self):
        with patch.dict(sys.modules, {"pyttsx3": self.fake_mod}):
            eng = Pyttsx3Engine(rate=150, volume=2.0, voice="zira")
            starts = []
            self.assertTrue(eng.speak("hello", on_start=lambda: starts.append(1)))
            inst = FakePyttsx3Engine.instances[-1]
            self.assertEqual(inst.spoken, ["hello"])
            self.assertEqual(starts, [1])
            self.assertEqual(inst.props["rate"], 150)
            self.assertEqual(inst.props["volume"], 1.0)
            self.assertEqual(inst.props["voice"], "v2")
            eng.shutdown()

    def test_list_voices(self):
        with patch.dict(sys.modules, {"pyttsx3": self.fake_mod}):
            eng = Pyttsx3Engine()
            self.assertEqual([v["name"] for v in eng.list_voices()], ["Microsoft David", "Microsoft Zira"])
            eng.shutdown()

    def test_interrupt_from_other_thread(self):
        with patch.dict(sys.modules, {"pyttsx3": self.fake_mod}):
            eng = Pyttsx3Engine()
            threading.Timer(0.05, eng.interrupt).start()
            self.fake_mod.init = lambda *a, **k: FakePyttsx3Engine(speak_ticks=10_000)
            eng._teardown_engine = lambda: None
            t0 = time.monotonic()
            self.assertFalse(eng.speak("a very long sentence"))
            self.assertLess(time.monotonic() - t0, 2)
            eng.shutdown()

    def test_works_through_manager_and_recreates_after_interrupt(self):
        with patch.dict(sys.modules, {"pyttsx3": self.fake_mod}):
            eng = Pyttsx3Engine()
            m = SpeechManager(eng, SpeechConfig())
            with m:
                m.say("one")
                m.wait_until_idle(3)
                m.say("two")
                m.wait_until_idle(3)
            spoken = [s for i in FakePyttsx3Engine.instances for s in i.spoken]
            self.assertEqual(spoken, ["one", "two"])

    def test_missing_library_gives_helpful_error(self):
        with patch.dict(sys.modules, {"pyttsx3": None}):
            eng = Pyttsx3Engine()
            with self.assertRaisesRegex(ImportError, "pip install pyttsx3"):
                eng.speak("x")
            eng.shutdown()


if __name__ == "__main__":
    unittest.main()
