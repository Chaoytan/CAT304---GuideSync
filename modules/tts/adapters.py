"""Input adapters: turn *whatever* upstream modules produce into ``Message`` objects.

Supported without any extra code:

* ``str``                         -> plain message (JSON strings are parsed)
* ``Message``                     -> used as is
* ``dict`` with "text"/"message"  -> text message (optional priority, key, kind, ttl...)
* ``dict`` detection              -> {"label": "chair", "confidence": 0.9, "bbox": [x1,y1,x2,y2],
                                      "frame_width": 640}
* ``dict`` marker / checkpoint    -> {"type": "marker", "marker_id": 2, "name": "Junction A",
                                      "route_text": "The planned route continues left."}
                                     status: "ok" (default) | "unknown" | "out_of_sequence"
* ``dict`` system event           -> {"type": "system", "event": "camera_lost"}
* objects with attributes         -> .label/.confidence/.bbox  or  .text/.priority
* Ultralytics YOLO ``Results``    -> anything with ``.boxes`` and ``.names``
* list / tuple / generator of any of the above (detections are grouped per label)

Anything else raises ``UnsupportedInputError``. Add your own with ``register_adapter``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from .message import (
    KIND_OBJECT,
    KIND_ROUTE,
    KIND_SYSTEM,
    KIND_TEXT,
    Message,
    Priority,
)


class UnsupportedInputError(TypeError):
    """Raised when no adapter understands the input."""


@dataclass
class AdapterOptions:
    """Knobs for the built-in adapters."""

    frame_width: Optional[float] = None       # used when a detection does not carry its own
    min_confidence: Optional[float] = None    # drop detections below this (None = keep all)
    labels: Optional[Iterable[str]] = None    # whitelist of labels (None = all)
    group_detections: bool = True             # "Two chairs" instead of two "Chair" messages
    include_position: bool = True             # "left of view"
    position_in_key: bool = False             # True -> moving objects count as new messages
    label_priorities: Mapping[str, Any] = field(default_factory=dict)  # e.g. {"person": "HIGH"}

    def __post_init__(self) -> None:
        if self.labels is not None:
            self.labels = {str(x).lower() for x in self.labels}


# --------------------------------------------------------------------------- phrases

SYSTEM_PHRASES: Dict[str, Tuple[str, Priority]] = {
    "camera_lost": ("Camera disconnected. Object announcements stopped.", Priority.CRITICAL),
    "camera_restored": ("Camera reconnected.", Priority.HIGH),
    "detector_error": ("Object detection has stopped.", Priority.CRITICAL),
    "audio_error": ("Audio problem detected.", Priority.CRITICAL),
    "low_light": ("Lighting is low. Detection may be unreliable.", Priority.HIGH),
    "marker_module_error": ("Checkpoint detection has stopped.", Priority.CRITICAL),
    "shutting_down": ("GuideSync is shutting down.", Priority.CRITICAL),
    "started": ("GuideSync is ready.", Priority.HIGH),
}

_NUMBER_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
                 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}
_IRREGULAR_PLURALS = {"person": "people"}

_LABEL_KEYS = ("label", "class_name", "class", "name", "cls_name")
_CONF_KEYS = ("confidence", "conf", "score")
_BOX_KEYS = ("bbox", "box", "xyxy")
_WIDTH_KEYS = ("frame_width", "image_width", "width")
_MARKER_ID_KEYS = ("marker_id", "aruco_id", "checkpoint_id", "tag_id")
_MARKER_TYPES = {"marker", "checkpoint", "aruco"}
_SYSTEM_TYPES = {"system", "status", "error", "failure", "event"}


@dataclass
class _Detection:
    label: str
    confidence: Optional[float]
    position: Optional[str]


# --------------------------------------------------------------------------- registry

_CUSTOM_ADAPTERS: List[Tuple[Callable[[Any], bool], Callable[[Any, AdapterOptions], Any]]] = []


def register_adapter(predicate: Callable[[Any], bool],
                     func: Callable[[Any, AdapterOptions], Any]) -> None:
    """Teach the module a new input type.

    ``predicate(raw)`` -> True if this adapter handles ``raw``.
    ``func(raw, options)`` -> str | Message | dict | list of those | None.
    Custom adapters are tried before the built-in ones. Whatever ``func`` returns is
    normalised again, so returning a plain string or dict is fine.
    """
    _CUSTOM_ADAPTERS.append((predicate, func))


def clear_custom_adapters() -> None:
    _CUSTOM_ADAPTERS.clear()


# --------------------------------------------------------------------------- public API

def normalize(raw: Any, options: Optional[AdapterOptions] = None) -> List[Message]:
    """Convert ``raw`` into a list of Messages. Raises UnsupportedInputError."""
    opts = options or AdapterOptions()
    items: List[Any] = []
    _collect(raw, opts, items, depth=0)
    return _finalise(items, opts)


# --------------------------------------------------------------------------- internals

def _collect(raw: Any, opts: AdapterOptions, out: List[Any], depth: int) -> None:
    if depth > 8:
        raise UnsupportedInputError("Input is nested too deeply")
    if raw is None:
        return

    for predicate, func in _CUSTOM_ADAPTERS:
        if predicate(raw):
            _collect(func(raw, opts), opts, out, depth + 1)
            return

    if isinstance(raw, Message):
        out.append(raw)
    elif isinstance(raw, (bytes, bytearray)):
        _collect(bytes(raw).decode("utf-8", errors="replace"), opts, out, depth + 1)
    elif isinstance(raw, str):
        _collect_str(raw, opts, out, depth)
    elif isinstance(raw, Mapping):
        _collect_mapping(raw, opts, out)
    elif hasattr(raw, "boxes") and hasattr(raw, "names"):
        _collect_ultralytics(raw, opts, out)
    elif _is_iterable(raw):
        for item in raw:
            _collect(item, opts, out, depth + 1)
    else:
        _collect_object(raw, opts, out)


def _is_iterable(raw: Any) -> bool:
    return hasattr(raw, "__iter__") or hasattr(raw, "__next__")


def _collect_str(text: str, opts: AdapterOptions, out: List[Any], depth: int) -> None:
    stripped = text.strip()
    if stripped[:1] in ("{", "["):
        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            _collect(parsed, opts, out, depth + 1)
            return
    if stripped:
        out.append(Message(text=stripped))


def _first(d: Mapping, keys: Tuple[str, ...]) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _collect_mapping(d: Mapping, opts: AdapterOptions, out: List[Any]) -> None:
    kind_value = str(d.get("type") or "").lower()
    alt_kind = str(d.get("kind") or "").lower()
    t = kind_value or (alt_kind if alt_kind in (_MARKER_TYPES | _SYSTEM_TYPES) else "")

    if t in _MARKER_TYPES or (not t and _first(d, _MARKER_ID_KEYS) is not None
                              and "text" not in d):
        out.append(_marker_message(d))
    elif t in _SYSTEM_TYPES and "text" not in d:
        out.append(_system_message(d))
    elif "text" in d or "message" in d:
        out.append(_text_message(d))
    elif _first(d, _LABEL_KEYS) is not None and (
            _first(d, _CONF_KEYS) is not None or _first(d, _BOX_KEYS) is not None):
        det = _detection_from_mapping(d, opts)
        if det is not None:
            out.append(det)
    else:
        raise UnsupportedInputError(f"Unrecognised dict keys: {sorted(map(str, d.keys()))}")


def _text_message(d: Mapping) -> Message:
    text = d.get("text", d.get("message"))
    msg = Message(text="" if text is None else str(text))
    if "priority" in d and d["priority"] is not None:
        msg.priority = Priority.parse(d["priority"])
    if d.get("key"):
        msg.key = str(d["key"])
    elif d.get("duplicate_key"):
        msg.key = str(d["duplicate_key"])
    if d.get("kind"):
        msg.kind = str(d["kind"])
    if d.get("ttl") is not None:
        msg.ttl = float(d["ttl"])
    if d.get("timestamp") is not None:
        msg.created_at = float(d["timestamp"])
    msg.interrupt = bool(d.get("interrupt", False))
    msg.bypass_cooldown = bool(d.get("bypass_cooldown", False))

    # Enrich ObstacleAnalyzer decisions (message + label + direction) and
    # Module 2 checkpoint/lounge events (text + duplicate_key + status) when
    # explicit kind/key were not provided.
    if not d.get("kind"):
        if "direction" in d and "label" in d and "message" in d:
            msg.kind = KIND_OBJECT
            if not d.get("key") and not d.get("duplicate_key"):
                prox = d.get("proximity", "")
                msg.key = f"obj:{str(d['label']).lower()}:{d['direction']}:{prox}".rstrip(":")
            msg.meta = {
                "label": d["label"],
                "direction": d["direction"],
                "proximity": d.get("proximity"),
            }
        elif "duplicate_key" in d and "status" in d:
            msg.kind = KIND_ROUTE
            if "priority" not in d or d["priority"] is None:
                msg.priority = Priority.HIGH
            msg.meta = {"status": d.get("status"), "seen": d.get("seen"), "expected": d.get("expected")}

    return msg


def _marker_message(d: Mapping) -> Message:
    marker_id = _first(d, _MARKER_ID_KEYS)
    name = _first(d, ("name", "checkpoint", "checkpoint_name", "label"))
    route = _first(d, ("route_text", "route", "instruction", "message"))
    status = str(d.get("status") or "ok").lower()

    if status in ("unknown", "unrecognised", "unrecognized") or (name is None and marker_id is None):
        text, prio, key = "Unrecognised marker.", Priority.NORMAL, "route:unknown"
    elif status in ("out_of_sequence", "out-of-sequence"):
        label = name if name is not None else f"Marker {marker_id}"
        text = f"{label} identified, but it is not the expected next checkpoint."
        prio, key = Priority.HIGH, f"route:{marker_id if marker_id is not None else name}:oos"
    else:
        label = name if name is not None else f"Marker {marker_id}"
        text = f"{label} identified."
        if route:
            text += f" {str(route).strip()}"
        prio, key = Priority.HIGH, f"route:{marker_id if marker_id is not None else name}"

    msg = Message(text=text, priority=prio, key=key, kind=KIND_ROUTE,
                  meta={"marker_id": marker_id, "status": status})
    if d.get("priority") is not None:
        msg.priority = Priority.parse(d["priority"])
    if d.get("timestamp") is not None:
        msg.created_at = float(d["timestamp"])
    return msg


def _system_message(d: Mapping) -> Message:
    event = str(_first(d, ("event", "code", "name", "status")) or "").strip()
    custom = d.get("message")
    if event in SYSTEM_PHRASES:
        text, prio = SYSTEM_PHRASES[event]
    else:
        pretty = event.replace("_", " ").strip() or "unspecified"
        text = f"System notice: {pretty}."
        prio = Priority.CRITICAL if str(d.get("type")).lower() in ("error", "failure") else Priority.HIGH
    if custom:
        text = str(custom)
    msg = Message(text=text, priority=prio, key=f"system:{event or 'generic'}",
                  kind=KIND_SYSTEM, meta={"event": event})
    if d.get("priority") is not None:
        msg.priority = Priority.parse(d["priority"])
    return msg


def _width_of(d: Mapping, opts: AdapterOptions) -> Optional[float]:
    w = _first(d, _WIDTH_KEYS)
    if w is None:
        shape = d.get("frame_shape") or d.get("image_shape")  # (h, w[, c])
        if shape is not None and len(shape) >= 2:
            w = shape[1]
    if w is None:
        w = opts.frame_width
    return float(w) if w else None


def _position_from_box(box: Any, width: Optional[float], fmt: str = "xyxy") -> Optional[str]:
    if box is None:
        return None
    try:
        x1, y1, a, b = [float(v) for v in list(box)[:4]]
    except (TypeError, ValueError):
        return None
    x2 = a if fmt == "xyxy" else x1 + a
    centre = (x1 + x2) / 2.0
    if width is None:
        if max(abs(x1), abs(x2)) <= 1.0:   # looks normalised 0..1
            width = 1.0
        else:
            return None
    ratio = centre / width
    if ratio < 1 / 3:
        return "left"
    if ratio > 2 / 3:
        return "right"
    return "centre"


def _detection_from_mapping(d: Mapping, opts: AdapterOptions) -> Optional[_Detection]:
    label = str(_first(d, _LABEL_KEYS))
    conf = _first(d, _CONF_KEYS)
    conf_f = float(conf) if conf is not None else None
    if not _passes(label, conf_f, opts):
        return None
    pos = _position_from_box(_first(d, _BOX_KEYS), _width_of(d, opts),
                             str(d.get("bbox_format", "xyxy")).lower())
    return _Detection(label=label, confidence=conf_f, position=pos)


def _passes(label: str, conf: Optional[float], opts: AdapterOptions) -> bool:
    if opts.min_confidence is not None and conf is not None and conf < opts.min_confidence:
        return False
    if opts.labels is not None and label.lower() not in opts.labels:
        return False
    return True


def _tolist(x: Any) -> list:
    return x.tolist() if hasattr(x, "tolist") else list(x)


def _collect_ultralytics(res: Any, opts: AdapterOptions, out: List[Any]) -> None:
    boxes = res.boxes
    if boxes is None:
        return
    names = res.names
    classes, confs, xyxy = _tolist(boxes.cls), _tolist(boxes.conf), _tolist(boxes.xyxy)
    shape = getattr(res, "orig_shape", None)
    width = float(shape[1]) if shape is not None and len(shape) >= 2 else opts.frame_width
    for c, cf, box in zip(classes, confs, xyxy):
        label = names[int(c)]
        if not _passes(label, float(cf), opts):
            continue
        out.append(_Detection(label, float(cf), _position_from_box(box, width)))


def _collect_object(raw: Any, opts: AdapterOptions, out: List[Any]) -> None:
    label = next((getattr(raw, k) for k in _LABEL_KEYS if getattr(raw, k, None) is not None), None)
    conf = next((getattr(raw, k) for k in _CONF_KEYS if getattr(raw, k, None) is not None), None)
    box = next((getattr(raw, k) for k in _BOX_KEYS if getattr(raw, k, None) is not None), None)
    text = getattr(raw, "text", None)

    if isinstance(text, str):
        d = {"text": text}
        for k in ("priority", "key", "kind", "ttl", "interrupt", "bypass_cooldown"):
            if getattr(raw, k, None) is not None:
                d[k] = getattr(raw, k)
        out.append(_text_message(d))
    elif label is not None and (conf is not None or box is not None):
        width = getattr(raw, "frame_width", None) or opts.frame_width
        conf_f = float(conf) if conf is not None else None
        if _passes(str(label), conf_f, opts):
            out.append(_Detection(str(label), conf_f,
                                  _position_from_box(box, float(width) if width else None)))
    else:
        raise UnsupportedInputError(
            f"Cannot turn {type(raw).__name__!r} into speech. Pass a string, dict, Message, "
            "detection, or register a custom adapter with register_adapter().")


# --------------------------------------------------------------------------- grouping

def _plural(label: str) -> str:
    low = label.lower()
    if low in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[low]
    if low.endswith(("s", "x", "ch", "sh")):
        return low + "es"
    return low + "s"


def _finalise(items: List[Any], opts: AdapterOptions) -> List[Message]:
    messages: List[Message] = []
    detections: List[_Detection] = []
    for it in items:
        (detections if isinstance(it, _Detection) else messages).append(it)

    if detections:
        messages.extend(_detections_to_messages(detections, opts))
    return messages


def _detections_to_messages(dets: List[_Detection], opts: AdapterOptions) -> List[Message]:
    groups: Dict[str, List[_Detection]] = {}
    for d in dets:
        key = d.label.lower().replace("_", " ")
        groups.setdefault(key, []).append(d)
        if not opts.group_detections:
            # unique bucket per detection, same message key afterwards
            groups[f"{key}#{len(groups[key])}"] = groups.pop(key)

    out: List[Message] = []
    for name, members in groups.items():
        base = name.split("#")[0]
        n = len(members)
        positions = {m.position for m in members}
        pos = positions.pop() if len(positions) == 1 else None
        conf = max((m.confidence for m in members if m.confidence is not None), default=None)

        subject = base.capitalize() if n == 1 else f"{_NUMBER_WORDS.get(n, str(n))} {_plural(base)}"
        if opts.include_position and pos:
            text = f"{subject}, {pos} of view."
        else:
            text = f"{subject} in view."

        key = f"obj:{base}"
        if opts.position_in_key and pos:
            key += f":{pos}"
        prio = Priority.NORMAL
        override = opts.label_priorities.get(base) or opts.label_priorities.get(base.replace(" ", "_"))
        if override is not None:
            prio = Priority.parse(override)
        out.append(Message(text=text, priority=prio, key=key, kind=KIND_OBJECT,
                           meta={"label": base, "count": n, "confidence": conf, "position": pos}))
    return out


__all__ = [
    "AdapterOptions", "SYSTEM_PHRASES", "UnsupportedInputError",
    "clear_custom_adapters", "normalize", "register_adapter",
]
_ = KIND_TEXT  # re-exported for convenience
