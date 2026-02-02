"""State machine for matching event streams against alarm profiles."""

import logging
from typing import List, Optional, Tuple

from ..events import AudioEvent, PatternMatchEvent, ToneEvent
from ..models import AlarmProfile

logger = logging.getLogger(__name__)


class MatcherState:
    """Tracks progress of a single profile match."""

    def __init__(self, profile: AlarmProfile):
        self.profile = profile
        self.current_segment_index = 0
        self.cycle_count = 0
        self.last_event_time = 0.0
        self.start_time = 0.0

        # Pre-compute the valid frequency range for this profile
        self.freq_ranges: List[Tuple[float, float]] = []
        for seg in profile.segments:
            if seg.type == "tone" and seg.frequency:
                self.freq_ranges.append((seg.frequency.min, seg.frequency.max))

    def reset(self):
        """Reset matching state."""
        self.current_segment_index = 0
        self.cycle_count = 0
        self.last_event_time = 0.0

    def is_relevant_frequency(self, freq: float) -> bool:
        """Check if a frequency is within any expected range for this profile."""
        for fmin, fmax in self.freq_ranges:
            if fmin <= freq <= fmax:
                return True
        return False


class SequenceMatcher:
    """Matches incoming events against multiple alarm profiles using a state machine.

    This class maintains an independent tracking state for each monitored profile.
    It receives audio events (like Tones) and sequentially verifies if they match
    the expected segments (Tones/Silences) of an alarm pattern.

    Key Features:
    - **Noise Immunity**: Tones that do not match ANY expected frequency range
      across the profile are ignored. This effectively makes the matcher "deaf"
      to background noise like speech or music, provided they don't overlap
      with alarm frequencies.
    - **Parallel Matching**: Can track multiple optional profiles simultaneously.
    - **Resilience**: Handles missing or imperfect events up to a certain tolerance.
    """

    def __init__(self, profiles: List[AlarmProfile]):
        """Initialize with list of profiles to match against.

        Args:
            profiles: List of AlarmProfile objects defining the patterns to detect.
        """
        self.profiles = profiles
        self.states = {p.name: MatcherState(p) for p in profiles}

    def process(self, event: AudioEvent) -> List[PatternMatchEvent]:
        """Process a new audio event and check for pattern matches.

        This is the main entry point for the matcher. It updates the state
        of every profile with the new event.

        Args:
            event: An AudioEvent (usually a ToneEvent) detected by the Generator.

        Returns:
            List of PatternMatchEvent objects for any profiles that completed
            their full pattern match sequence with this event.
        """
        matches = []

        for profile in self.profiles:
            match_event = self._update_profile(self.states[profile.name], event)
            if match_event:
                matches.append(match_event)

        return matches

    def _update_profile(
        self, state: MatcherState, event: AudioEvent
    ) -> Optional[PatternMatchEvent]:
        """Update matching state for a single profile.

        Internal method that advances the state machine for a specific profile.

        Args:
            state: The tracking state for the profile.
            event: The new audio event to evaluate.

        Returns:
            A PatternMatchEvent if the profile's confirmation cycles are complete,
            otherwise None.
        """
        p = state.profile

        if state.current_segment_index >= len(p.segments):
            state.current_segment_index = 0

        expected = p.segments[state.current_segment_index]

        if isinstance(event, ToneEvent):
            # KEY FIX: Ignore tones that don't match any expected frequency
            # This filters out ambient noise that would break pattern matching
            if not state.is_relevant_frequency(event.frequency):
                # This tone is outside all expected ranges - ignore it completely
                logger.debug(f"[{p.name}] Ignoring out-of-band tone: {event.frequency:.0f}Hz")
                return None

            # Check silence gap before this tone
            gap_duration = event.timestamp - state.last_event_time

            # If expecting silence, check if gap matches
            if expected.type == "silence":
                # Handle overlapping events (negative gap)
                # If we have a negative gap, it means this new event started BEFORE the previous one ended.
                # If this new event matches the PREVIOUSLY matched tone segment, we can treat it as part of that event
                # and just extend the timeline, effectively merging them.
                if gap_duration < 0 and state.current_segment_index > 0:
                    prev_idx = state.current_segment_index - 1
                    # Wrap around not needed because index increments only after silence
                    # Wait, if current is silence, previous was TONE.
                    prev_seg = p.segments[prev_idx]

                    if prev_seg.type == "tone" and prev_seg.frequency:
                        if prev_seg.frequency.contains(event.frequency):
                            # This is likely a parallel detection of the previous tone
                            logger.debug(
                                f"[{p.name}] Merging overlapping tone: {event.frequency:.0f}Hz "
                                f"(gap {gap_duration:.2f}s)"
                            )
                            # Extend the last event time if this one lasts longer
                            state.last_event_time = max(
                                state.last_event_time, event.timestamp + event.duration
                            )
                            return None

                if expected.duration.contains(gap_duration):
                    state.current_segment_index += 1
                    logger.debug(f"[{p.name}] Silence matched: {gap_duration:.2f}s")

                    if state.current_segment_index >= len(p.segments):
                        state.cycle_count += 1
                        state.current_segment_index = 0
                        logger.debug(
                            f"[{p.name}] Cycle {state.cycle_count}/{p.confirmation_cycles} complete"
                        )

                        if state.cycle_count >= p.confirmation_cycles:
                            state.cycle_count = 0
                            return PatternMatchEvent(
                                timestamp=event.timestamp,
                                duration=0,
                                profile_name=p.name,
                                cycle_count=p.confirmation_cycles,
                            )

                    expected = p.segments[state.current_segment_index]
                else:
                    if state.current_segment_index > 0:
                        logger.debug(
                            f"[{p.name}] Reset: Gap {gap_duration:.2f}s doesn't match "
                            f"expected {expected.duration.min:.2f}-{expected.duration.max:.2f}s"
                        )
                        state.reset()
                        expected = p.segments[0]

            # Now check if this tone matches current expectation
            is_match = False
            if expected.type == "tone" and expected.frequency:
                freq_match = expected.frequency.contains(event.frequency)
                dur_match = expected.duration.contains(event.duration)

                if freq_match and dur_match:
                    is_match = True
                    logger.debug(
                        f"[{p.name}] Tone matched step {state.current_segment_index}: "
                        f"{event.frequency:.0f}Hz, {event.duration:.2f}s"
                    )
                elif freq_match and not dur_match:
                    # Frequency matches but duration doesn't - reset
                    logger.debug(
                        f"[{p.name}] Duration mismatch: got {event.duration:.2f}s, "
                        f"expected {expected.duration.min:.2f}-{expected.duration.max:.2f}s"
                    )
                    if state.current_segment_index > 0:
                        state.reset()
                        expected = p.segments[0]
                        # Try matching step 0 with this event
                        if (
                            expected.type == "tone"
                            and expected.frequency
                            and expected.frequency.contains(event.frequency)
                            and expected.duration.contains(event.duration)
                        ):
                            is_match = True

            # Advance state if matched
            if is_match:
                state.last_event_time = event.timestamp + event.duration
                state.current_segment_index += 1

                if state.current_segment_index >= len(p.segments):
                    state.cycle_count += 1
                    state.current_segment_index = 0
                    logger.debug(
                        f"[{p.name}] Cycle {state.cycle_count}/{p.confirmation_cycles} complete"
                    )

                    if state.cycle_count >= p.confirmation_cycles:
                        state.cycle_count = 0
                        return PatternMatchEvent(
                            timestamp=event.timestamp,
                            duration=0,
                            profile_name=p.name,
                            cycle_count=p.confirmation_cycles,
                        )

        return None
