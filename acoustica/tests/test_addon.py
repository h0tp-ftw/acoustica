"""End-to-end add-on tests that need no microphone or Home Assistant."""

from __future__ import annotations

import json
import os
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

from acoustic_engine.config import AudioSettings
from acoustic_engine.parallel_engine import ParallelEngine
from acoustic_engine.presets import load_preset

from detector.config import load_app_config
from detector.ha_bridge import HABridge

SAMPLE_RATE = 44100
CHUNK = 1024


def _tone(freq: float, dur: float, amp: int = 12000) -> np.ndarray:
    timeline = np.arange(int(SAMPLE_RATE * dur)) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * freq * timeline)).astype(np.int16)


def _silence(dur: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * dur), dtype=np.int16)


def _t3_smoke_audio(freq: float = 3100.0, cycles: int = 4) -> np.ndarray:
    cycle = np.concatenate(
        [
            _tone(freq, 0.5),
            _silence(0.5),
            _tone(freq, 0.5),
            _silence(0.5),
            _tone(freq, 0.5),
            _silence(1.4),
        ]
    )
    return np.tile(cycle, cycles)


def _write_wav(path: Path, audio: np.ndarray) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio.tobytes())


class FakeClient:
    def __init__(self) -> None:
        self.updates: list[tuple[str, str, bool]] = []
        self.disconnected = False

    def connect(self) -> bool:
        return True

    def start(self) -> None:
        return None

    def publish_discovery(self) -> bool:
        return True

    def update_state(self, name: str, device_class: str, active: bool) -> bool:
        self.updates.append((name, device_class, active))
        return True

    def status(self) -> dict[str, object]:
        return {"connected": True, "pending_updates": 0}

    def update_addon_options(self, options) -> bool:
        return True

    def disconnect(self) -> None:
        self.disconnected = True


def test_config_building(monkeypatch, tmp_path) -> None:
    """Preset, profile YAML, and learned WAV all become detectors."""

    data_dir = tmp_path / "acoustica"
    (data_dir / "profiles").mkdir(parents=True)
    (data_dir / "sounds").mkdir(parents=True)

    (data_dir / "profiles" / "buzzer.yaml").write_text(
        "name: Buzzer\n"
        "confirmation_cycles: 1\n"
        "segments:\n"
        "  - type: tone\n"
        "    frequency: {min: 950, max: 1050}\n"
        "    duration: {min: 0.2, max: 0.5}\n"
        "  - type: silence\n"
        "    duration: {min: 0.1, max: 0.4}\n",
        encoding="utf-8",
    )

    wav = data_dir / "sounds" / "washer.wav"
    learn_cycle = np.concatenate(
        [_tone(1500, 0.3), _silence(0.15), _tone(1500, 0.3), _silence(0.9)]
    )
    _write_wav(wav, np.tile(learn_cycle, 3))

    options = {
        "detectors": [
            {"name": "Smoke", "preset": "smoke_t3", "device_class": "smoke"},
            {"name": "Buzzer", "profile": "buzzer.yaml", "device_class": "sound"},
            {"name": "Washer", "learn": "washer.wav", "device_class": "running"},
        ],
        "sample_rate": 44100,
        "hold_seconds": 5,
    }
    options_path = tmp_path / "options.json"
    options_path.write_text(json.dumps(options), encoding="utf-8")
    monkeypatch.setenv("OPTIONS_JSON", str(options_path))
    monkeypatch.setenv("ACOUSTIC_DATA_DIR", str(data_dir))

    config = load_app_config()
    names = {spec.profile.name: spec.device_class for spec in config.detectors}
    assert names == {"Smoke": "smoke", "Buzzer": "sound", "Washer": "running"}
    washer = next(spec for spec in config.detectors if spec.profile.name == "Washer")
    assert any(segment.type == "tone" for segment in washer.profile.segments)
    assert config.hold_seconds == 5


def test_detection_reaches_non_blocking_home_assistant_bridge() -> None:
    """A real T3 match queues ON and then OFF without HTTP in the audio loop."""

    client = FakeClient()
    bridge = HABridge(
        device_classes={"Smoke Alarm": "smoke"},
        hold_seconds=0.2,
        client=client,
    )
    assert bridge.setup() is True
    assert client.updates == [("Smoke Alarm", "smoke", False)]

    profile = load_preset("smoke_t3")
    profile.name = "Smoke Alarm"
    engine = ParallelEngine(
        pipelines=[profile],
        audio_config=AudioSettings(sample_rate=SAMPLE_RATE, chunk_size=CHUNK),
        on_detection=bridge.on_detection,
    )

    audio = _t3_smoke_audio()
    for index in range(0, len(audio) - CHUNK, CHUNK):
        engine.process_chunk(audio[index : index + CHUNK])

    assert ("Smoke Alarm", "smoke", True) in client.updates
    time.sleep(0.35)
    assert client.updates[-1] == ("Smoke Alarm", "smoke", False)

    bridge.shutdown()
    assert client.disconnected is True
