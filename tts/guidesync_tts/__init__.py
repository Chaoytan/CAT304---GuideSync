"""GuideSync text-to-speech module.

Quick start::

    from guidesync_tts import create_manager

    with create_manager() as tts:                      # real voice via pyttsx3
        tts.submit("Hello")                            # plain text
        tts.submit({"label": "chair", "confidence": 0.9,
                    "bbox": [100, 50, 300, 400], "frame_width": 640})   # detection
        tts.submit({"type": "marker", "marker_id": 1, "name": "Junction A",
                    "route_text": "The planned route continues left."}) # checkpoint
        tts.wait_until_idle()
"""
from .adapters import (
    AdapterOptions,
    UnsupportedInputError,
    clear_custom_adapters,
    normalize,
    register_adapter,
)
from .engine import ConsoleEngine, FakeEngine, Pyttsx3Engine, SpeechEngine
from .manager import SpeechConfig, SpeechManager, SubmitResult
from .message import Message, Priority


def create_manager(engine: str = "pyttsx3", config: "SpeechConfig | None" = None,
                   rate: "int | None" = None, volume: "float | None" = None,
                   voice: "str | None" = None, **kwargs) -> SpeechManager:
    """Convenience factory. engine: "pyttsx3" (real voice), "console" (print only) or "fake"."""
    if engine == "pyttsx3":
        eng: SpeechEngine = Pyttsx3Engine(rate=rate, volume=volume, voice=voice)
        eng.check()  # fail fast at start-up if there is no voice / library
    elif engine == "console":
        eng = ConsoleEngine()
    elif engine == "fake":
        eng = FakeEngine()
    else:
        raise ValueError(f"Unknown engine {engine!r}")
    return SpeechManager(eng, config, **kwargs)


__all__ = [
    "AdapterOptions", "ConsoleEngine", "FakeEngine", "Message", "Priority", "Pyttsx3Engine",
    "SpeechConfig", "SpeechEngine", "SpeechManager", "SubmitResult", "UnsupportedInputError",
    "clear_custom_adapters", "create_manager", "normalize", "register_adapter",
]
