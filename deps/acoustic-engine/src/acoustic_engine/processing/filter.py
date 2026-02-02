"""Frequency filter for pre-filtering spectral peaks."""

from typing import List, Optional, Tuple

from ..models import AlarmProfile
from .dsp import Peak


class FrequencyFilter:
    """Filters spectral peaks to only include relevant frequencies.

    This sits between the DSP layer (which detects all peaks) and the
    Generator (which creates events). By filtering early, we reduce
    processing overhead and prevent irrelevant tones from cluttering
    the event stream.
    """

    def __init__(self, profiles: Optional[List[AlarmProfile]] = None):
        """Initialize with profiles to extract frequency ranges from.

        Args:
            profiles: List of AlarmProfiles. Frequency ranges are extracted
                     from all tone segments in all profiles.
        """
        self.freq_ranges: List[Tuple[float, float]] = []

        if profiles:
            self._extract_ranges(profiles)

    def _extract_ranges(self, profiles: List[AlarmProfile]):
        """Extract all expected frequency ranges from profiles."""
        for profile in profiles:
            for segment in profile.segments:
                if segment.type == "tone" and segment.frequency:
                    self.freq_ranges.append((segment.frequency.min, segment.frequency.max))

        # Merge overlapping ranges for efficiency
        if self.freq_ranges:
            self.freq_ranges = self._merge_overlapping(self.freq_ranges)

    def _merge_overlapping(self, ranges: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Merge overlapping frequency ranges."""
        if not ranges:
            return []

        # Sort by start frequency
        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        merged = [sorted_ranges[0]]

        for current in sorted_ranges[1:]:
            last = merged[-1]
            # If current overlaps or is adjacent to last, merge them
            if current[0] <= last[1] + 50:  # 50Hz tolerance for "adjacent"
                merged[-1] = (last[0], max(last[1], current[1]))
            else:
                merged.append(current)

        return merged

    def add_range(self, freq_min: float, freq_max: float):
        """Add a frequency range to filter for.

        Args:
            freq_min: Minimum frequency in Hz
            freq_max: Maximum frequency in Hz
        """
        self.freq_ranges.append((freq_min, freq_max))
        self.freq_ranges = self._merge_overlapping(self.freq_ranges)

    def is_relevant(self, frequency: float) -> bool:
        """Check if a frequency falls within any expected range.

        Args:
            frequency: Frequency in Hz to check

        Returns:
            True if the frequency is within at least one expected range
        """
        for fmin, fmax in self.freq_ranges:
            if fmin <= frequency <= fmax:
                return True
        return False

    def filter_peaks(self, peaks: List[Peak]) -> List[Peak]:
        """Filter a list of peaks to only include relevant frequencies.

        Args:
            peaks: List of Peak objects from DSP

        Returns:
            Filtered list containing only peaks with relevant frequencies
        """
        if not self.freq_ranges:
            # No filtering configured - pass through all peaks
            return peaks

        return [p for p in peaks if self.is_relevant(p.frequency)]

    def __repr__(self) -> str:
        ranges_str = ", ".join(f"{fmin:.0f}-{fmax:.0f}Hz" for fmin, fmax in self.freq_ranges)
        return f"FrequencyFilter([{ranges_str}])"
