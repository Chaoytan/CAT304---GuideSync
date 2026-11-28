import tempfile
import time
import unittest
from pathlib import Path

from modules.tts import FakeEngine, Priority, SpeechConfig, SpeechManager


def make(duration=0.0, **cfg):
    eng = FakeEngine(duration=duration)
    config = SpeechConfig(**cfg)
    return eng, SpeechManager(eng, config)


def chair(x=320):
    return {"label": "chair", "confidence": 0.9, "bbox": [x - 20, 0, x + 20, 50], "frame_width": 640}


class TestTtsManager(unittest.TestCase):
    def test_speaks_plain_text(self):
        eng, m = make()
        with m:
            m.say("Hello")
            self.assertTrue(m.wait_until_idle(2))
        self.assertEqual(eng.spoken, ["Hello"])
        self.assertTrue(eng.shut_down)

    def test_empty_rejected(self):
        eng, m = make()
        with m:
            (r,) = m.submit("hello")
            self.assertTrue(r.accepted)
            self.assertEqual(m.submit({"text": "   "})[0].reason, "empty")

    def test_cooldown_suppresses_repeats(self):
        eng, m = make(cooldown_s=0.5)
        with m:
            m.submit(chair())
            m.wait_until_idle(2)
            r = m.submit(chair())[0]
            self.assertEqual((r.accepted, r.reason), (False, "cooldown"))
            time.sleep(0.55)
            self.assertTrue(m.submit(chair())[0].accepted)
            m.wait_until_idle(2)
        self.assertEqual(len(eng.spoken), 2)

    def test_no_unchanged_repeat_inside_cooldown_even_when_flooded(self):
        eng, m = make(duration=0.05, cooldown_s=0.4)
        with m:
            end = time.monotonic() + 1.2
            while time.monotonic() < end:
                m.submit(chair())
                time.sleep(0.01)
            m.wait_until_idle(2)
        onsets = eng.started_at
        self.assertGreaterEqual(len(onsets), 2)
        self.assertTrue(all(b - a >= 0.4 for a, b in zip(onsets, onsets[1:])))

    def test_baseline_without_suppression_speaks_everything(self):
        eng, m = make(suppression=False, cooldown_s=60, max_queue=50)
        with m:
            for _ in range(5):
                m.submit(chair())
            m.wait_until_idle(2)
        self.assertEqual(len(eng.spoken), 5)

    def test_priority_order(self):
        eng, m = make()
        eng.duration = 0.3
        with m:
            m.say("first")
            time.sleep(0.05)
            m.say("low", priority="LOW")
            m.say("high", priority="HIGH")
            m.say("normal")
            m.wait_until_idle(3)
        self.assertEqual(eng.spoken, ["first", "high", "normal", "low"])

    def test_oldest_first_within_same_priority(self):
        eng, m = make(duration=0.2)
        with m:
            m.say("block")
            time.sleep(0.05)
            m.say("a")
            m.say("b")
            m.say("c")
            m.wait_until_idle(3)
        self.assertEqual(eng.spoken, ["block", "a", "b", "c"])

    def test_stale_object_message_not_spoken(self):
        eng, m = make(duration=0.4)
        with m:
            m.say("blocker")
            time.sleep(0.05)
            m.submit(chair())
            m.submit({"label": "bottle", "confidence": 0.9}, ttl=0.1)
            m.wait_until_idle(3)
        self.assertNotIn("Bottle in view.", eng.spoken)
        self.assertTrue(any(e["reason"] == "expired" for e in m.get_log() if e["event"] == "dropped"))

    def test_already_old_input_is_rejected_on_submit(self):
        eng, m = make()
        with m:
            r = m.submit(chair(), created_at=time.monotonic() - 5)[0]
            self.assertEqual((r.accepted, r.reason), (False, "expired"))

    def test_queue_is_bounded_and_drops_lowest_priority(self):
        eng, m = make(duration=0.3, max_queue=2)
        with m:
            m.say("block")
            time.sleep(0.05)
            m.say("n1")
            m.say("n2")
            r = m.say("low", priority="LOW")[0]
            self.assertEqual(r.reason, "queue_full")
            m.say("hi", priority="HIGH")
            self.assertLessEqual(m.pending_count, 2)
            m.wait_until_idle(3)
        self.assertNotIn("low", eng.spoken)
        self.assertIn("hi", eng.spoken)

    def test_duplicate_in_queue_is_replaced_not_stacked(self):
        eng, m = make(duration=0.3)
        with m:
            m.say("block")
            time.sleep(0.05)
            m.submit(chair(100))
            r = m.submit(chair(500))[0]
            self.assertEqual(r.reason, "replaced")
            self.assertEqual(m.pending_count, 1)
            m.wait_until_idle(3)
        self.assertEqual(eng.spoken.count("Chair, left of view.") + eng.spoken.count("Chair, right of view."), 1)
        self.assertIn("Chair, right of view.", eng.spoken)

    def test_critical_interrupts_current_speech(self):
        eng, m = make(duration=1.0)
        with m:
            m.say("long routine message")
            time.sleep(0.1)
            m.submit({"type": "system", "event": "camera_lost"})
            m.wait_until_idle(3)
        self.assertEqual(eng.interrupted_texts, ["long routine message"])
        self.assertEqual(eng.spoken, ["Camera disconnected. Object announcements stopped."])

    def test_normal_does_not_interrupt(self):
        eng, m = make(duration=0.3)
        with m:
            m.say("one")
            time.sleep(0.05)
            m.say("two")
            m.wait_until_idle(3)
        self.assertEqual(eng.spoken, ["one", "two"])
        self.assertFalse(eng.interrupted_texts)

    def test_pause_blocks_routine_and_interrupts(self):
        eng, m = make(duration=1.0)
        with m:
            m.say("routine")
            time.sleep(0.1)
            m.pause()
            m.wait_until_idle(2)
            self.assertEqual(m.submit("later")[0].reason, "paused")
            self.assertTrue(m.submit({"type": "system", "event": "audio_error"})[0].accepted)
            m.wait_until_idle(3)
            m.resume()
            self.assertTrue(m.submit("after resume")[0].accepted)
            m.wait_until_idle(3)
        self.assertEqual(eng.interrupted_texts, ["routine"])
        self.assertNotIn("later", eng.spoken)
        self.assertIn("after resume", eng.spoken)

    def test_repeat_and_summary_bypass_cooldown_and_pause(self):
        eng, m = make(cooldown_s=60)
        with m:
            m.submit(chair(100))
            m.wait_until_idle(2)
            m.pause()
            m.repeat_last()
            m.wait_until_idle(2)
            m.request_summary()
            m.wait_until_idle(2)
        self.assertEqual(eng.spoken, ["Chair, left of view."] * 3)

    def test_repeat_with_nothing_said_and_empty_summary(self):
        eng, m = make()
        with m:
            m.repeat_last()
            m.request_summary()
            m.wait_until_idle(2)
        self.assertEqual(eng.spoken, ["Nothing to repeat.", "Nothing detected."])

    def test_summary_combines_recent_objects_even_if_suppressed(self):
        eng, m = make(cooldown_s=60)
        with m:
            m.submit([chair(100), {"label": "bottle", "confidence": 0.9, "bbox": [500, 0, 540, 40], "frame_width": 640}])
            m.wait_until_idle(2)
            m.submit(chair(100))
            m.request_summary()
            m.wait_until_idle(2)
        summary = eng.spoken[-1]
        self.assertIn("Chair, left of view.", summary)
        self.assertIn("Bottle, right of view.", summary)

    def test_cancel_pending_for_camera_loss(self):
        eng, m = make(duration=0.3)
        with m:
            m.say("block")
            time.sleep(0.05)
            m.submit(chair())
            m.submit({"label": "bottle", "confidence": 0.9})
            m.say("keep me", kind="route")
            self.assertEqual(m.cancel_pending(["object"], interrupt_current=False), 2)
            m.wait_until_idle(3)
        self.assertEqual(eng.spoken, ["block", "keep me"])

    def test_engine_failure_does_not_kill_worker(self):
        eng, m = make()
        eng.fail_next(RuntimeError("audio device gone"))
        with m:
            m.say("lost")
            m.wait_until_idle(2)
            m.say("works")
            m.wait_until_idle(2)
            self.assertEqual(m.stats()["engine_failures"], 0)
        self.assertEqual(eng.spoken, ["works"])
        self.assertTrue(any(e["event"] == "engine_error" for e in m.get_log()))

    def test_stats_latency_and_export(self):
        eng, m = make(duration=0.02)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with m:
                m.say("a")
                m.say("b")
                m.wait_until_idle(2)
                s = m.stats()
                self.assertEqual(s["spoken"], 2)
                self.assertIsNotNone(s["latency_median_s"])
                self.assertGreaterEqual(s["latency_p95_s"], s["latency_median_s"])
                m.export_log(str(tmp_path / "log.csv"))
                m.export_log(str(tmp_path / "log.json"))
            self.assertTrue((tmp_path / "log.csv").read_text(encoding="utf-8").startswith("t,event"))
            self.assertTrue((tmp_path / "log.json").exists())

    def test_submit_overrides_and_list_input(self):
        eng, m = make(duration=0.0)
        with m:
            res = m.submit(["x", "y"], priority="HIGH", key="same")
            self.assertEqual([r.message.priority for r in res], [Priority.HIGH] * 2)
            m.wait_until_idle(2)

    def test_closed_manager_rejects(self):
        eng, m = make()
        m.close()
        self.assertEqual(m.submit("late")[0].reason, "closed")

    def test_on_event_callback_errors_are_ignored(self):
        eng = FakeEngine()
        seen = []

        def cb(e):
            seen.append(e["event"])
            raise RuntimeError("bad callback")

        m = SpeechManager(eng, on_event=cb)
        with m:
            m.say("hi")
            m.wait_until_idle(2)
        self.assertIn("spoken", seen)
        self.assertEqual(eng.spoken, ["hi"])


if __name__ == "__main__":
    unittest.main()
