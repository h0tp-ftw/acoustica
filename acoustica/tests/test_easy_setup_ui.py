from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
JS = (ROOT / "tuner" / "acoustica-controls.js").read_text(encoding="utf-8")
CSS = (ROOT / "tuner" / "acoustica-controls.css").read_text(encoding="utf-8")


def test_beginner_wizard_has_five_plain_language_steps() -> None:
    expected_copy = [
        "Make sure Acoustica can hear",
        "What does this sound mean?",
        "Teach Acoustica the sound",
        "Test it with a fresh recording",
        "Save and start listening",
    ]
    for text in expected_copy:
        assert text in JS
    assert "Step ${state.step} of 5" in JS
    assert "without editing YAML" in JS


def test_beginner_flow_calls_only_host_microphone_apis() -> None:
    for endpoint in [
        "api/acoustica/setup/microphone-check",
        "api/acoustica/setup/learn",
        "api/acoustica/setup/tune",
        "api/acoustica/setup/test",
        "api/acoustica/setup/save-and-enable",
    ]:
        assert endpoint in JS

    forbidden_browser_capture = [
        "getUserMedia",
        "MediaRecorder",
        "navigator.mediaDevices",
    ]
    for forbidden in forbidden_browser_capture:
        assert forbidden not in JS


def test_save_requires_a_successful_fresh_test() -> None:
    assert "Pass a fresh test before saving this detector." in JS
    assert "state.testResult && state.testResult.detected" in JS
    assert "The detector needs to pass a fresh test before it can be saved." in JS


def test_layperson_can_tweak_without_raw_frequency_controls() -> None:
    assert "Forgiving" in JS
    assert "Balanced" in JS
    assert "Precise" in JS
    assert "Make matching more forgiving" in JS
    beginner_copy, advanced_copy = JS.lower().split("need frequency", 1)
    assert "frequency" not in beginner_copy
    assert "advanced tuner" in advanced_copy


def test_advanced_tuner_is_preserved_but_hidden_by_default() -> None:
    assert 'data-action="advanced"' in JS
    assert "document.body.classList.add(\"acoustica-simple-mode\")" in JS
    assert "body.acoustica-simple-mode #root" in CSS
    assert "body:not(.acoustica-simple-mode) #acoustica-easy-setup" in CSS
    assert "#acoustica-return-simple" in CSS


def test_easy_setup_is_mobile_and_accessibility_aware() -> None:
    assert "aria-live=\"polite\"" in JS
    assert "acoustica-sr-only" in JS
    assert "@media (max-width: 520px)" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert ":focus-visible" in CSS
