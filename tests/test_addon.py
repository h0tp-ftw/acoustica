"""Add-on tests that need no microphone and no Home Assistant.

Two things are verified end to end:

1. ``load_app_config`` builds the right detectors from add-on options for all
   three sources (preset, profile YAML, learn-from-recording).
2. A real detection flows through the engine into the HABridge and out as the
   HTTP event Home Assistant would receive — ON on detection, OFF after the hold.

Run directly (``python tests/test_addon.py``) or under pytest. Requires the
``acoustic-engine`` package to be installed.
"""

import http.server
import json
import os
import socketserver
import tempfile
import threading
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


# --------------------------------------------------------------------------- #
# synthetic audio helpers
# --------------------------------------------------------------------------- #
def _tone(freq: float, dur: float, amp: int = 12000) -> np.ndarray:
    t = np.arange(int(SAMPLE_RATE * dur)) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def _silence(dur: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * dur), dtype=np.int16)


def _t3_smoke_audio(freq: float = 3100.0, cycles: int = 4) -> np.ndarray:
    """A T3 pattern: beep-beep-beep, long gap, repeated."""
    cycle = np.concatenate([
        _tone(freq, 0.5), _silence(0.5),
        _tone(freq, 0.5), _silence(0.5),
        _tone(freq, 0.5), _silence(1.4),
    ])
    return np.tile(cycle, cycles)


def _write_wav(path: Path, audio: np.ndarray) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())


# --------------------------------------------------------------------------- #
# mock Home Assistant event endpoint
# --------------------------------------------------------------------------- #
class _MockHA:
    """Captures the JSON events the bridge POSTs, on a free localhost port."""

    def __init__(self):
        self.events = []
        parent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                parent.events.append({
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "data": json.loads(body) if body else {},
                })
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):  # silence
                pass

        self._server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def by_name(self, name: str):
        return [e["data"] for e in self.events if e["data"].get("name") == name]


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_config_building():
    """Preset + profile YAML + learned WAV all become detectors."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "acoustic_alarm_detector"
        (data_dir / "profiles").mkdir(parents=True)
        (data_dir / "sounds").mkdir(parents=True)

        # A custom profile YAML (a 1000 Hz two-beep pattern).
        profile_yaml = data_dir / "profiles" / "buzzer.yaml"
        profile_yaml.write_text(
            "name: Buzzer\n"
            "confirmation_cycles: 1\n"
            "segments:\n"
            "  - type: tone\n    frequency: {min: 950, max: 1050}\n    duration: {min: 0.2, max: 0.5}\n"
            "  - type: silence\n    duration: {min: 0.1, max: 0.4}\n"
        )

        # A recording to learn from (a repeating 1500 Hz beep).
        wav = data_dir / "sounds" / "washer.wav"
        learn_cycle = np.concatenate([
            _tone(1500, 0.3), _silence(0.15), _tone(1500, 0.3), _silence(0.9),
        ])
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
        opts_path = tmp / "options.json"
        opts_path.write_text(json.dumps(options))

        os.environ["OPTIONS_JSON"] = str(opts_path)
        os.environ["ACOUSTIC_DATA_DIR"] = str(data_dir)

        cfg = load_app_config()

        names = {s.profile.name: s.device_class for s in cfg.detectors}
        assert "Smoke" in names and names["Smoke"] == "smoke", names
        assert "Buzzer" in names and names["Buzzer"] == "sound", names
        assert "Washer" in names and names["Washer"] == "running", names
        # The learned profile must actually have tone segments.
        washer = next(s for s in cfg.detectors if s.profile.name == "Washer")
        assert any(seg.type == "tone" for seg in washer.profile.segments)
        assert cfg.hold_seconds == 5
        print(f"  config: built {len(cfg.detectors)} detectors -> {list(names)}")


def test_detection_reaches_home_assistant():
    """A T3 alarm fires an ON event, then an OFF event after the hold."""
    with _MockHA() as ha:
        bridge = HABridge(
            device_classes={"Smoke Alarm": "smoke"},
            hold_seconds=1.0,
            base_url=ha.base_url,
            token="test-token",
            profiles_path=str(Path(tempfile.mkdtemp()) / "profiles.json"),
        )
        bridge.setup()

        # setup() writes discovery + pushes an initial OFF for the sensor.
        assert Path(bridge.profiles_path).exists(), "discovery file not written"
        assert ha.by_name("Smoke Alarm") == [{"name": "Smoke Alarm", "state": False, "device_class": "smoke"}], \
            "expected one initial OFF event"

        # Rename the preset before building the engine so the match's
        # profile_name is the sensor name (this is what config.py does too).
        profile = load_preset("smoke_t3")
        profile.name = "Smoke Alarm"
        engine = ParallelEngine(
            pipelines=[profile],
            audio_config=AudioSettings(sample_rate=SAMPLE_RATE, chunk_size=CHUNK),
            on_detection=bridge.on_detection,
        )

        audio = _t3_smoke_audio()
        for i in range(0, len(audio) - CHUNK, CHUNK):
            engine.process_chunk(audio[i : i + CHUNK])

        on_events = [e for e in ha.by_name("Smoke Alarm") if e["state"] is True]
        assert on_events, f"no ON event fired; got {ha.by_name('Smoke Alarm')}"
        assert on_events[0]["device_class"] == "smoke"
        # Authorization header must carry the bearer token.
        assert any(e["auth"] == "Bearer test-token" for e in ha.events)
        print(f"  detection: ON fired ({len(on_events)} ON event(s))")

        # After the hold expires, the bridge should clear the sensor.
        time.sleep(1.4)
        off_after_on = [e for e in ha.by_name("Smoke Alarm") if e["state"] is False]
        assert len(off_after_on) >= 2, f"expected an OFF after the hold; got {ha.by_name('Smoke Alarm')}"
        print("  detection: OFF fired after hold")

        bridge.shutdown()


def _run():
    for name, fn in [
        ("test_config_building", test_config_building),
        ("test_detection_reaches_home_assistant", test_detection_reaches_home_assistant),
    ]:
        print(f"RUN {name}")
        fn()
        print(f"PASS {name}\n")
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    _run()
