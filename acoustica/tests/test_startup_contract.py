from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_startup_reports_microphone_gain_without_mutating_it() -> None:
    script = (ROOT / "run.sh").read_text(encoding="utf-8")

    assert "pactl get-source-mute" in script
    assert "pactl get-source-volume" in script
    assert "pactl set-source-mute" not in script
    assert "pactl set-source-volume" not in script


def test_tuner_process_has_a_bounded_restart_loop() -> None:
    script = (ROOT / "run.sh").read_text(encoding="utf-8")

    assert "run_tuner()" in script
    assert "restarting in 5 seconds" in script
    assert "sleep 5" in script


def test_runtime_panel_surfaces_recovery_errors() -> None:
    javascript = (ROOT / "tuner" / "acoustica-controls.js").read_text(
        encoding="utf-8"
    )

    assert "status.last_error" in javascript
    assert "automatic recovery" in javascript
