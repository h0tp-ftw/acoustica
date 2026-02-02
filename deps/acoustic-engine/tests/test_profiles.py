"""Tests for YAML profile loading."""


from acoustic_engine.models import AlarmProfile, Range, Segment
from acoustic_engine.profiles import (
    load_profile_from_yaml,
    save_profile_to_yaml,
)

SAMPLE_YAML = """
name: "TestAlarm"
confirmation_cycles: 2
segments:
  - type: "tone"
    frequency:
      min: 2900
      max: 3100
    duration:
      min: 0.4
      max: 0.6
  - type: "silence"
    duration:
      min: 0.1
      max: 0.3
"""


class TestLoadProfile:
    def test_load_single_profile(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        profile = load_profile_from_yaml(yaml_file)

        assert profile.name == "TestAlarm"
        assert profile.confirmation_cycles == 2
        assert len(profile.segments) == 2

    def test_load_tone_segment(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        profile = load_profile_from_yaml(yaml_file)
        tone = profile.segments[0]

        assert tone.type == "tone"
        assert tone.frequency.min == 2900
        assert tone.frequency.max == 3100
        assert tone.duration.min == 0.4
        assert tone.duration.max == 0.6

    def test_load_silence_segment(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        profile = load_profile_from_yaml(yaml_file)
        silence = profile.segments[1]

        assert silence.type == "silence"
        assert silence.frequency is None
        assert silence.duration.min == 0.1


class TestSaveProfile:
    def test_save_and_reload(self, tmp_path):
        original = AlarmProfile(
            name="SaveTest",
            segments=[
                Segment(type="tone", frequency=Range(1000, 1200), duration=Range(0.3, 0.5)),
                Segment(type="silence", duration=Range(0.1, 0.2)),
            ],
            confirmation_cycles=3,
        )

        yaml_file = tmp_path / "saved.yaml"
        save_profile_to_yaml(original, yaml_file)

        loaded = load_profile_from_yaml(yaml_file)

        assert loaded.name == original.name
        assert loaded.confirmation_cycles == original.confirmation_cycles
        assert len(loaded.segments) == len(original.segments)
