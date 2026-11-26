"""Lounge route for the prepared entrance-facing approach and opposite return approach."""
import json
from pathlib import Path


class LoungeRoute:
    ids = (10, 20, 30, 40, 50, 60)
    dictionary_name = "DICT_4X4_100"
    # state: (marker, next state). The junction has a separate two-key choice.
    stops = {"entrance": (10, "choice"), "dead_end": (40, "return"),
             "return": (30, "turn"), "turn": (50, "destination"),
             "destination": (60, "complete")}

    def __init__(self):
        self.cues = json.loads(Path(__file__).with_name("lounge.json").read_text(encoding="utf-8"))
        self.reset()

    def reset(self):
        self.state = "entrance"
        self.pending = None
        self.choice_ready = False

    def observe(self, ids):
        """Observe only. A new observation cancels permission from the previous frame."""
        seen = sorted(set(ids))
        self.pending = None
        self.choice_ready = False
        expected = self.stops.get(self.state, (None,))[0]
        event = dict(state=self.state, seen=seen, expected=expected, text=None)
        pair = seen == [20, 30]
        if self.state == "complete":
            status = "complete"
        elif not seen:
            status = "not_visible"
        elif self.state == "choice" and pair:
            status = "choice_visible"
            self.choice_ready = True
        elif expected is not None and (seen == [expected] or (self.state == "return" and pair)):
            status = "expected_visible"
            self.pending = expected
        elif self.state == "choice" and seen in ([20], [30]):
            status = "partial_junction"
        elif len(seen) > 1:
            status = "ambiguous"
        elif seen[0] not in self.ids:
            status = "unknown"
        else:
            status = "out_of_order"
        if status in ("choice_visible", "expected_visible"):
            event.update(name=self.state, text=self.cues[self.state],
                         duplicate_key="lounge:" + self.state)
        return dict(event, status=status)

    def confirm(self, marker_id):
        """Confirm a visible ordinary checkpoint, never a choice."""
        if self.pending is None or self.pending != marker_id:
            return False
        self.state = self.stops[self.state][1]
        self.pending = None
        return True

    def choose(self, side):
        """Return a single cue event for the selected branch, or None if invalid."""
        if not self.choice_ready or side not in ("left", "right"):
            return None
        self.choice_ready = False
        self.state = "dead_end" if side == "left" else "turn"
        return dict(status="branch_selected", name=side, seen=[20, 30], expected=None,
                    text=self.cues[side], duplicate_key="lounge:choice:" + side)
