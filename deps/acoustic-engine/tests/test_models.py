"""Tests for core models."""

from acoustic_engine.models import AlarmProfile, Range, Segment


class TestRange:
    def test_contains_within(self):
        r = Range(min=10, max=20)
        assert r.contains(15) is True

    def test_contains_at_boundaries(self):
        r = Range(min=10, max=20)
        assert r.contains(10) is True
        assert r.contains(20) is True

    def test_contains_outside(self):
        r = Range(min=10, max=20)
        assert r.contains(5) is False
        assert r.contains(25) is False


class TestSegment:
    def test_tone_segment_str(self):
        seg = Segment(type="tone", frequency=Range(2900, 3100), duration=Range(0.4, 0.6))
        s = str(seg)
        assert "Tone" in s
        assert "2900" in s
        assert "3100" in s

    def test_silence_segment_str(self):
        seg = Segment(type="silence", duration=Range(0.1, 0.3))
        s = str(seg)
        assert "Silence" in s


class TestAlarmProfile:
    def test_create_profile(self):
        profile = AlarmProfile(
            name="TestAlarm",
            segments=[
                Segment(type="tone", frequency=Range(3000, 3100), duration=Range(0.5, 0.5)),
                Segment(type="silence", duration=Range(0.2, 0.2)),
            ],
            confirmation_cycles=2,
        )

        assert profile.name == "TestAlarm"
        assert len(profile.segments) == 2
        assert profile.confirmation_cycles == 2
