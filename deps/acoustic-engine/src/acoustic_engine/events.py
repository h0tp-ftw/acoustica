"""Event definitions for the detection pipeline."""

from dataclasses import dataclass


@dataclass
class AudioEvent:
    """Base class for all audio events."""

    timestamp: float
    duration: float


@dataclass
class ToneEvent(AudioEvent):
    """Represents a detected tone.

    Attributes:
        timestamp: When the tone started (seconds)
        duration: How long the tone lasted (seconds)
        frequency: Dominant frequency of the tone (Hz)
        magnitude: Peak FFT magnitude
        confidence: Detection confidence (0-1)
    """

    frequency: float
    magnitude: float
    confidence: float = 1.0


@dataclass
class SilenceEvent(AudioEvent):
    """Represents a period of silence (or non-target noise)."""

    pass


@dataclass
class PatternMatchEvent(AudioEvent):
    """Represents a successful pattern match.

    Attributes:
        timestamp: When the match was confirmed
        duration: Total duration of the matched pattern
        profile_name: Name of the matched alarm profile
        cycle_count: Number of cycles that were matched
    """

    profile_name: str
    cycle_count: int
