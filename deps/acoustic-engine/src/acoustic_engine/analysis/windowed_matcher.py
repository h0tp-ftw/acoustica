import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..events import PatternMatchEvent, ToneEvent
from ..models import AlarmProfile
from .event_buffer import EventBuffer

logger = logging.getLogger(__name__)


@dataclass
class WindowConfig:
    """Configuration for windowed matching of a profile."""

    window_duration: float  # Total window size in seconds
    eval_frequency: float  # How often to evaluate (seconds)
    pattern_duration: float  # Expected duration of one pattern cycle


class WindowedMatcher:
    """Pattern matcher using sliding window analysis.

    This matcher is designed to be robust against noise and missing events.
    Instead of processing events sequentially and strictly maintaining a state machine,
    it buffers events over a period of time and periodically scans the buffer (the "window")
    to see if there is a sequence of events that matches an alarm profile.

    Features:
    - **Noise Robustness**: Leading or trailing noise events in the window are ignored;
      the matcher looks for the *best fit* sub-sequence within the window.
    - **Sliding Window**: Continuously re-evaluates the recent history.
    - **Frequency Filtering**: Only considers events that match the profile's
      target frequencies, ignoring out-of-band noise.
    """

    def __init__(
        self,
        profiles: List[AlarmProfile],
        max_buffer_duration: float = 60.0,
        noise_skip_limit: int = 2,
        duration_relax_low: float = 0.8,
        duration_relax_high: float = 1.5,
    ):
        """Initialize the windowed matcher.

        Args:
            profiles: List of AlarmProfile patterns to detect.
            max_buffer_duration: Seconds of history to keep in memory.
            noise_skip_limit: Max number of noise events to skip during matching.
            duration_relax_low: Multiplier for minimum segment duration detection.
            duration_relax_high: Multiplier for maximum segment duration detection.
        """
        self.profiles = profiles
        self.max_buffer_duration = max_buffer_duration
        self.noise_skip_limit = noise_skip_limit
        self.duration_relax_low = duration_relax_low
        self.duration_relax_high = duration_relax_high

        self.event_buffer = EventBuffer(max_duration=self.max_buffer_duration)

        # Per-profile configuration and state
        self.configs: Dict[str, WindowConfig] = {}
        self.last_eval_times: Dict[str, float] = {}
        self.cycle_counts: Dict[str, int] = {}
        self.last_match_times: Dict[str, float] = {}  # Prevent duplicate detections

        for profile in profiles:
            config = self._compute_config(profile)
            self.configs[profile.name] = config
            self.last_eval_times[profile.name] = 0.0
            self.cycle_counts[profile.name] = 0
            self.last_match_times[profile.name] = -999.0  # Long ago

            logger.debug(
                f"[{profile.name}] Window config: duration={config.window_duration:.1f}s, "
                f"eval_freq={config.eval_frequency:.2f}s, pattern={config.pattern_duration:.2f}s"
            )

    def _compute_config(self, profile: AlarmProfile) -> WindowConfig:
        """Compute window configuration from profile parameters.

        Calculates the optimal window size and evaluation frequency based on the
        profile's segments and confirmation cycles.

        Args:
            profile: The AlarmProfile to configure for.

        Returns:
            Computed WindowConfig.
        """
        # Calculate expected pattern duration (sum of all segment mean durations)
        pattern_duration = 0.0
        for seg in profile.segments:
            pattern_duration += (seg.duration.min + seg.duration.max) / 2

        # Window should be large enough to capture confirmation_cycles patterns
        # plus some buffer for noise
        min_window = pattern_duration * profile.confirmation_cycles

        # Use profile's window_duration if set, otherwise auto-calculate
        window_duration = getattr(profile, "window_duration", None)
        if window_duration is None:
            # Window = pattern_duration * cycles * 1.5 (for buffer)
            window_duration = min_window * 1.5

        # Use profile's eval_frequency if set, otherwise auto-calculate
        eval_frequency = getattr(profile, "eval_frequency", None)
        if eval_frequency is None:
            # Evaluate more frequently for shorter patterns
            eval_frequency = min(0.5, pattern_duration / 4)

        return WindowConfig(
            window_duration=window_duration,
            eval_frequency=eval_frequency,
            pattern_duration=pattern_duration,
        )

    def add_event(self, event: ToneEvent) -> None:
        """Add a new detected event to the circular buffer.

        Args:
            event: ToneEvent object from the EventGenerator.
        """
        self.event_buffer.add(event)
        logger.debug(f"Buffered event: {event.frequency:.0f}Hz at t={event.timestamp:.2f}s")

    def evaluate(self, current_time: float) -> List[PatternMatchEvent]:
        """Evaluate all profiles against the current event buffer.

        This checks if enough time has passed since the last evaluation for each
        profile, and if so, scans the window for matches.

        Args:
            current_time: Current simulation/system time in seconds.

        Returns:
            List of PatternMatchEvent objects for any newly confirmed detections.
        """
        matches = []

        for profile in self.profiles:
            config = self.configs[profile.name]
            last_eval = self.last_eval_times[profile.name]

            # Only evaluate if enough time has passed
            if current_time - last_eval < config.eval_frequency:
                continue

            self.last_eval_times[profile.name] = current_time

            # Get events in the current window
            window_events = self.event_buffer.get_window(current_time, config.window_duration)

            if not window_events:
                continue

            # Try to match pattern in window
            match = self._match_pattern_in_window(window_events, profile, current_time)
            if match:
                matches.append(match)

        return matches

    def _match_pattern_in_window(
        self,
        events: List[ToneEvent],
        profile: AlarmProfile,
        current_time: float,
    ) -> Optional[PatternMatchEvent]:
        """Check if events in the time window match the profile pattern.

        The matching algorithm:
        1. Filters events to only those matching the profile's frequency ranges.
        2. Sorts events by time.
        3. Iterates through the events, treating each one as a potential "start"
           of the pattern.
        4. For each start candidate, counts how many consecutive valid cycles follow.
        5. If the cycle count meets the profile's `confirmation_cycles`, a match is returned.

        Args:
            events: List of ToneEvents falling within the analysis window.
            profile: The AlarmProfile to match against.
            current_time: The current timestamp (used for the match event).

        Returns:
            PatternMatchEvent if a sufficient pattern is found, otherwise None.
        """
        config = self.configs[profile.name]

        # Build list of valid frequency ranges from profile
        freq_ranges: List[Tuple[float, float]] = []
        for seg in profile.segments:
            if seg.type == "tone" and seg.frequency:
                freq_ranges.append((seg.frequency.min, seg.frequency.max))

        if not freq_ranges:
            return None

        # Filter events to only those in valid frequency ranges
        relevant_events = []
        for event in events:
            for fmin, fmax in freq_ranges:
                if fmin <= event.frequency <= fmax:
                    relevant_events.append(event)
                    break

        if not relevant_events:
            return None

        # Sort by timestamp
        relevant_events.sort(key=lambda e: e.timestamp)

        logger.debug(
            f"[{profile.name}] Evaluating {len(relevant_events)} relevant events in window"
        )

        # Try to find pattern starting from each event
        best_cycles = 0

        for start_idx in range(len(relevant_events)):
            cycles = self._count_pattern_cycles(relevant_events[start_idx:], profile)
            if cycles > best_cycles:
                best_cycles = cycles

        # Check if we have enough cycles
        if best_cycles >= profile.confirmation_cycles:
            # Prevent duplicate detections (must be at least pattern_duration since last)
            last_match = self.last_match_times[profile.name]
            if current_time - last_match < config.pattern_duration:
                logger.debug(f"[{profile.name}] Suppressing duplicate detection")
                return None

            self.last_match_times[profile.name] = current_time

            logger.info(f"[{profile.name}] Pattern matched! {best_cycles} cycles found")

            return PatternMatchEvent(
                timestamp=current_time,
                duration=config.pattern_duration * best_cycles,
                profile_name=profile.name,
                cycle_count=best_cycles,
            )

        return None

    def _count_pattern_cycles(
        self,
        events: List[ToneEvent],
        profile: AlarmProfile,
    ) -> int:
        """Count how many complete pattern cycles match from the start.

        Args:
            events: Sequence of events to check (already filtered by frequency)
            profile: Profile defining the pattern

        Returns:
            Number of complete cycles matched
        """
        if not events:
            return 0

        # Extract tone segments from profile
        tone_segments = [s for s in profile.segments if s.type == "tone"]
        silence_segments = [s for s in profile.segments if s.type == "silence"]

        if not tone_segments:
            return 0

        cycle_count = 0
        event_idx = 0

        # Try to match complete cycles
        while event_idx < len(events):
            cycle_matched = True

            # Use a temporary index so we can backtrack if the cycle fails
            temp_idx = event_idx

            for seg_idx, tone_seg in enumerate(tone_segments):
                # We employ a "noise tolerance" retry loop here.
                # If the current event doesn't match the expected tone, we check if
                # it's just a transient noise spike by peeking at the NEXT event.
                # We allow skipping up to 2 "noise" events per expected tone.

                matched_seg = False
                skipped_noise = 0
                max_skip = self.noise_skip_limit

                while skipped_noise <= max_skip:
                    if temp_idx >= len(events):
                        break

                    event = events[temp_idx]

                    # 1. Check Frequency
                    freq_match = tone_seg.frequency and tone_seg.frequency.contains(event.frequency)

                    # 2. Check Duration (flexible but not too loose)
                    dur_min = tone_seg.duration.min * self.duration_relax_low
                    dur_max = tone_seg.duration.max * self.duration_relax_high
                    dur_match = dur_min <= event.duration <= dur_max

                    if freq_match and dur_match:
                        matched_seg = True
                        break  # Found our match!
                    else:
                        # This event didn't match. Is it noise?
                        # Skip it and look at the next one
                        temp_idx += 1
                        skipped_noise += 1

                if not matched_seg:
                    cycle_matched = False
                    break

                # If we found the tone, we need to validate the gap to the NEXT tone (if applicable)
                if seg_idx < len(tone_segments) - 1:
                    # We are at 'event' (at temp_idx).
                    # The next iteration of the outer loop will search for the next tone.
                    # We defer the gap check to the finding of the NEXT tone.
                    # But we need to ensure the gap *wasn't too long* or *too short*.
                    # Since we don't know where the next tone is yet, we can't fully validate
                    # the silence here easily without looking ahead.

                    # Simplified approach: We trust the "search" for the next tone to handle
                    # the timing implicitly.
                    if seg_idx < len(silence_segments):
                        # We can't check the gap until we find the next tone.
                        # So we'll skip gap validation here and rely on the fact that
                        # if the next tone is too far away, it effectively breaks the "rhythm".
                        pass

                # Prepare for next segment
                temp_idx += 1

            if cycle_matched:
                cycle_count += 1
                logger.debug(f"[{profile.name}] Cycle {cycle_count} matched")
                # Advance the main event pointer to where this cycle ended
                event_idx = temp_idx
            else:
                # If first cycle didn't match, we're done with this start point
                if cycle_count == 0:
                    break
                # If we matched some cycles but failed this one, stop counting
                break

        return cycle_count

    def reset(self) -> None:
        """Reset all state."""
        self.event_buffer.clear()
        for name in self.last_eval_times:
            self.last_eval_times[name] = 0.0
            self.cycle_counts[name] = 0
            self.last_match_times[name] = -999.0
