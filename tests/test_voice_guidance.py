import time
import unittest

from modules.voice_guidance import PrintBackend, VoiceGuidance


def wait_for(predicate, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestVoice(unittest.TestCase):
    def make(self, min_gap=0.0):
        self.backend = PrintBackend()
        return VoiceGuidance(backend_factory=lambda: self.backend, min_gap=min_gap).start()

    def test_speaks_decision(self):
        v = self.make()
        v.speak({"message": "Person ahead", "direction": "centre", "priority": "high"})
        self.assertTrue(wait_for(lambda: self.backend.spoken == ["Person ahead"]))
        v.stop()

    def test_muted_does_not_speak(self):
        v = self.make()
        v.mute()
        v.speak("Hello")
        time.sleep(0.2)
        self.assertEqual(self.backend.spoken, [])
        v.unmute()
        v.speak("Hello again")
        self.assertTrue(wait_for(lambda: "Hello again" in self.backend.spoken))
        v.stop()

    def test_none_is_ignored(self):
        v = self.make()
        v.speak(None)
        time.sleep(0.1)
        self.assertEqual(self.backend.spoken, [])
        v.stop()


if __name__ == "__main__":
    unittest.main()
