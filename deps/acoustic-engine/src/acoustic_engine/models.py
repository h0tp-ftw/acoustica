"""Data models for alarm pattern definitions."""

from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class Range:
    """A numeric range (min, max)."""

    min: float
    max: float

    def contains(self, value: float) -> bool:
        """Check if value falls within this range."""
        return self.min <= value <= self.max

    def __repr__(self) -> str:
        return f"Range({self.min}, {self.max})"


@dataclass
class ResolutionConfig:
    """Resolution settings for event detection.

    Lower values = higher resolution but more noise sensitivity.
    Higher values = more noise resilient but may merge fast patterns.

    Attributes:
        min_tone_duration: Minimum duration for a tone to count (filters clicks/pops)
        dropout_tolerance: Max gap before tone is considered ended
    """

    min_tone_duration: float = 0.1  # seconds
    dropout_tolerance: float = 0.15  # seconds

    @classmethod
    def high_resolution(cls) -> "ResolutionConfig":
        """Preset for fast patterns with small gaps (<100ms)."""
        return cls(min_tone_duration=0.05, dropout_tolerance=0.05)

    @classmethod
    def standard(cls) -> "ResolutionConfig":
        """Preset for standard patterns, noise-resilient."""
        return cls(min_tone_duration=0.1, dropout_tolerance=0.15)


@dataclass
class Segment:
    """A single step in an alarm pattern.

    Attributes:
        type: Either 'tone', 'silence', or 'any'
        frequency: Expected frequency range for tones (Hz)
        min_magnitude: Minimum FFT magnitude to consider valid
        duration: Expected duration range (seconds)
    """

    type: Literal["tone", "silence", "any"]

    # Tone specific
    frequency: Optional[Range] = None  # Hz
    min_magnitude: float = 0.05

    # Timing
    duration: Range = field(default_factory=lambda: Range(0, 999))

    def __str__(self) -> str:
        if self.type == "tone" and self.frequency:
            return f"Tone({self.frequency.min}-{self.frequency.max}Hz, {self.duration.min}-{self.duration.max}s)"
        elif self.type == "silence":
            return f"Silence({self.duration.min}-{self.duration.max}s)"
        return f"Any({self.duration.min}-{self.duration.max}s)"


@dataclass
class AlarmProfile:
    """Definition of an alarm pattern.

    Attributes:
        name: Unique identifier for this profile
        segments: Ordered list of Tone/Silence segments defining the pattern
        confirmation_cycles: How many full pattern repeats required for detection
        reset_timeout: Seconds of silence before resetting pattern matching
        window_duration: Optional window size for windowed matching (auto-calculated if None)
        eval_frequency: How often to evaluate windows in seconds (default 0.5)
        resolution: Resolution settings for event detection (optional, uses finest needed if None)
    """

    name: str
    segments: List[Segment]
    confirmation_cycles: int = 1
    reset_timeout: float = 10.0

    # Windowed matching parameters (optional, auto-calculated if not set)
    window_duration: Optional[float] = None  # Total window size in seconds
    eval_frequency: float = 0.5  # How often to evaluate (seconds)

    # Resolution settings (optional, per-profile override)
    resolution: Optional[ResolutionConfig] = None

    def __repr__(self) -> str:
        return f"AlarmProfile('{self.name}', {len(self.segments)} segments, {self.confirmation_cycles} cycles)"
