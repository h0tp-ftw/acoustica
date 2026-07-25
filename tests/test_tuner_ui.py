from __future__ import annotations

from pathlib import Path


def test_guided_ui_exposes_live_test_and_activation_without_browser_dsp() -> None:
    index = Path("tuner/index.html").read_text(encoding="utf-8")
    app = Path("tuner/app.js").read_text(encoding="utf-8")
    audio = Path("tuner/audio-engine.js").read_text(encoding="utf-8")

    assert 'id="runtimeListening"' in index
    assert 'id="runtimeHomeAssistant"' in index
    assert 'id="runtimeLastDetection"' in index
    assert 'id="microphoneSelect"' in index
    assert 'id="applyMicrophone"' in index
    assert 'id="activationCategory"' in index
    assert 'id="activeProfile"' in index
    assert "Live test" in app
    assert "renderRuntimeStatus" in app
    assert "api/audio/devices" in app
    assert "api/audio/select?device_index=" in app
    assert "/activate?alarm_type=" in app
    assert "getUserMedia" not in app + audio
    assert "AudioContext" not in app + audio
    assert "_estimateFrequency" not in app + audio
