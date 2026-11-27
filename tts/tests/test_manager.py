import time

import pytest

from guidesync_tts import FakeEngine, Priority, SpeechConfig, SpeechManager


def make(duration=0.0, **cfg):
    eng = FakeEngine(duration=duration)
    config = SpeechConfig(**cfg)
    return eng, SpeechManager(eng, config)


def chair(x=320):
    return {"label": "chair", "confidence": 0.9, "bbox": [x - 20, 0, x + 20, 50], "frame_width": 640}


def test_speaks_plain_text():
    eng, m = make()
    with m:
        m.say("Hello")
        assert m.wait_until_idle(2)
    assert eng.spoken == ["Hello"]
    assert eng.shut_down


def test_empty_rejected():
    eng, m = make()
    with m:
        (r,) = m.submit("hello")
        assert r.accepted
        assert m.submit({"text": "   "})[0].reason == "empty"


def test_cooldown_suppresses_repeats():
    eng, m = make(cooldown_s=0.5)
    with m:
        m.submit(chair()); m.wait_until_idle(2)
        r = m.submit(chair())[0]
        assert (r.accepted, r.reason) == (False, "cooldown")
        time.sleep(0.55)
        assert m.submit(chair())[0].accepted
        m.wait_until_idle(2)
    assert len(eng.spoken) == 2


def test_no_unchanged_repeat_inside_cooldown_even_when_flooded():
    eng, m = make(duration=0.05, cooldown_s=0.4)
    with m:
        end = time.monotonic() + 1.2
        while time.monotonic() < end:
            m.submit(chair())
            time.sleep(0.01)
        m.wait_until_idle(2)
    onsets = eng.started_at
    assert len(onsets) >= 2
    assert all(b - a >= 0.4 for a, b in zip(onsets, onsets[1:]))


def test_baseline_without_suppression_speaks_everything():
    eng, m = make(suppression=False, cooldown_s=60, max_queue=50)
    with m:
        for _ in range(5):
            m.submit(chair())
        m.wait_until_idle(2)
    assert len(eng.spoken) == 5


def test_priority_order():
    eng, m = make()
    # block the worker with a long utterance, then queue three
    eng.duration = 0.3
    with m:
        m.say("first")
        time.sleep(0.05)
        m.say("low", priority="LOW")
        m.say("high", priority="HIGH")
        m.say("normal")
        m.wait_until_idle(3)
    assert eng.spoken == ["first", "high", "normal", "low"]


def test_oldest_first_within_same_priority():
    eng, m = make(duration=0.2)
    with m:
        m.say("block")
        time.sleep(0.05)
        m.say("a"); m.say("b"); m.say("c")
        m.wait_until_idle(3)
    assert eng.spoken == ["block", "a", "b", "c"]


def test_stale_object_message_not_spoken():
    eng, m = make(duration=0.4)
    with m:
        m.say("blocker")
        time.sleep(0.05)
        m.submit(chair())              # object ttl default 2 s -> make it shorter
        m.submit({"label": "bottle", "confidence": 0.9}, ttl=0.1)
        m.wait_until_idle(3)
    assert "Bottle in view." not in eng.spoken
    assert any(e["reason"] == "expired" for e in m.get_log() if e["event"] == "dropped")


def test_already_old_input_is_rejected_on_submit():
    eng, m = make()
    with m:
        r = m.submit(chair(), created_at=time.monotonic() - 5)[0]
        assert (r.accepted, r.reason) == (False, "expired")


def test_queue_is_bounded_and_drops_lowest_priority():
    eng, m = make(duration=0.3, max_queue=2)
    with m:
        m.say("block")
        time.sleep(0.05)
        m.say("n1"); m.say("n2")
        r = m.say("low", priority="LOW")[0]
        assert r.reason == "queue_full"
        m.say("hi", priority="HIGH")        # evicts oldest of the lowest, n-something
        assert m.pending_count <= 2
        m.wait_until_idle(3)
    assert "low" not in eng.spoken and "hi" in eng.spoken


def test_duplicate_in_queue_is_replaced_not_stacked():
    eng, m = make(duration=0.3)
    with m:
        m.say("block")
        time.sleep(0.05)
        m.submit(chair(100)); r = m.submit(chair(500))[0]
        assert r.reason == "replaced" and m.pending_count == 1
        m.wait_until_idle(3)
    assert eng.spoken.count("Chair, left of view.") + eng.spoken.count("Chair, right of view.") == 1
    assert "Chair, right of view." in eng.spoken       # the newer one won


def test_critical_interrupts_current_speech():
    eng, m = make(duration=1.0)
    with m:
        m.say("long routine message")
        time.sleep(0.1)
        m.submit({"type": "system", "event": "camera_lost"})
        m.wait_until_idle(3)
    assert eng.interrupted_texts == ["long routine message"]
    assert eng.spoken == ["Camera disconnected. Object announcements stopped."]


def test_normal_does_not_interrupt():
    eng, m = make(duration=0.3)
    with m:
        m.say("one"); time.sleep(0.05); m.say("two")
        m.wait_until_idle(3)
    assert eng.spoken == ["one", "two"] and not eng.interrupted_texts


def test_pause_blocks_routine_and_interrupts():
    eng, m = make(duration=1.0)
    with m:
        m.say("routine"); time.sleep(0.1)
        m.pause()
        m.wait_until_idle(2)
        assert m.submit("later")[0].reason == "paused"
        assert m.submit({"type": "system", "event": "audio_error"})[0].accepted
        m.wait_until_idle(3)
        m.resume()
        assert m.submit("after resume")[0].accepted
        m.wait_until_idle(3)
    assert eng.interrupted_texts == ["routine"]
    assert "later" not in eng.spoken and "after resume" in eng.spoken


def test_repeat_and_summary_bypass_cooldown_and_pause():
    eng, m = make(cooldown_s=60)
    with m:
        m.submit(chair(100)); m.wait_until_idle(2)
        m.pause()
        m.repeat_last(); m.wait_until_idle(2)
        m.request_summary(); m.wait_until_idle(2)
    assert eng.spoken == ["Chair, left of view.", "Chair, left of view.", "Chair, left of view."]


def test_repeat_with_nothing_said_and_empty_summary():
    eng, m = make()
    with m:
        m.repeat_last(); m.request_summary(); m.wait_until_idle(2)
    assert eng.spoken == ["Nothing to repeat.", "Nothing detected."]


def test_summary_combines_recent_objects_even_if_suppressed():
    eng, m = make(cooldown_s=60)
    with m:
        m.submit([chair(100), {"label": "bottle", "confidence": 0.9, "bbox": [500, 0, 540, 40], "frame_width": 640}])
        m.wait_until_idle(2)
        m.submit(chair(100))     # suppressed by cooldown but still part of the scene
        m.request_summary(); m.wait_until_idle(2)
    summary = eng.spoken[-1]
    assert "Chair, left of view." in summary and "Bottle, right of view." in summary


def test_cancel_pending_for_camera_loss():
    eng, m = make(duration=0.3)
    with m:
        m.say("block")
        time.sleep(0.05)
        m.submit(chair()); m.submit({"label": "bottle", "confidence": 0.9})
        m.say("keep me", kind="route")
        assert m.cancel_pending(["object"], interrupt_current=False) == 2
        m.wait_until_idle(3)
    assert eng.spoken == ["block", "keep me"]


def test_engine_failure_does_not_kill_worker():
    eng, m = make()
    eng.fail_next(RuntimeError("audio device gone"))
    with m:
        m.say("lost")
        m.wait_until_idle(2)
        m.say("works")
        m.wait_until_idle(2)
        assert m.stats()["engine_failures"] == 0   # reset after a success
    assert eng.spoken == ["works"]
    assert any(e["event"] == "engine_error" for e in m.get_log())


def test_stats_latency_and_export(tmp_path):
    eng, m = make(duration=0.02)
    with m:
        m.say("a"); m.say("b"); m.wait_until_idle(2)
        s = m.stats()
        assert s["spoken"] == 2 and s["latency_median_s"] is not None
        assert s["latency_p95_s"] >= s["latency_median_s"]
        m.export_log(str(tmp_path / "log.csv"))
        m.export_log(str(tmp_path / "log.json"))
    assert (tmp_path / "log.csv").read_text().startswith("t,event")
    assert (tmp_path / "log.json").exists()


def test_submit_overrides_and_list_input():
    eng, m = make(duration=0.0)
    with m:
        res = m.submit(["x", "y"], priority="HIGH", key="same")
        assert [r.message.priority for r in res] == [Priority.HIGH] * 2
        m.wait_until_idle(2)


def test_closed_manager_rejects():
    eng, m = make()
    m.close()
    assert m.submit("late")[0].reason == "closed"


def test_on_event_callback_errors_are_ignored():
    eng = FakeEngine()
    seen = []

    def cb(e):
        seen.append(e["event"])
        raise RuntimeError("bad callback")

    m = SpeechManager(eng, on_event=cb)
    with m:
        m.say("hi"); m.wait_until_idle(2)
    assert "spoken" in seen and eng.spoken == ["hi"]
