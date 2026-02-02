"""Generates discrete events from continuous DSP data."""

import logging
from dataclasses import dataclass
from typing import List

from ..events import AudioEvent, ToneEvent
from ..processing.dsp import Peak

logger = logging.getLogger(__name__)


@dataclass
class ActiveTone:
    """Tracks a currently playing tone."""

    start_time: float
    frequency: float
    max_magnitude: float
    last_seen_time: float
    last_strong_time: float  # Last time the signal was above 50% of max
    last_magnitude: float  # Last chunk's magnitude for dip detection
    samples_count: int


class EventGenerator:
    """Converts continuous spectral peaks into discrete Tone/Silence events.

    This class acts as the bridge between the DSP layer (frequency peaks) and
    the pattern matchers (audio events). It handles:
    - **Debouncing**: Ignoring short transient noises.
    - **Continuity**: Stitching together spectral peaks across multiple
      chunks into coherent `ToneEvent`s.
    - **Dropout Tolerance**: Allowing short gaps in a signal (due to noise
      or interference) without breaking the tone event.
    - **Temporal Sorting**: Ensuring events are emitted in strict chronological order.
    """

    def __init__(
        self,
        sample_rate: int,
        chunk_size: int,
        min_tone_duration: float = 0.1,
        dropout_tolerance: float = 0.15,
        frequency_tolerance: float = 50.0,
        freq_smoothing: float = 0.3,
        dip_threshold: float = 0.6,
        strong_signal_ratio: float = 0.5,
        coalesce_ratio: float = 0.5,
    ):
        """Initialize the event generator.

        Args:
            sample_rate: Audio sample rate in Hz.
            chunk_size: Number of samples per chunk.
            min_tone_duration: Minimum duration for a detected tone to be valid.
            dropout_tolerance: Maximum silence gap allowed within a single tone.
            frequency_tolerance: Hz range to consider peaks as the same tone.
            freq_smoothing: Alpha for EMA frequency tracking.
            dip_threshold: Ratio for instantaneous dip detection.
            strong_signal_ratio: Ratio to consider signal "strong" for duration.
            coalesce_ratio: Overlap ratio for merging concurrent events.
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.chunk_duration = chunk_size / sample_rate

        # Safeguard: Ensure dropout tolerance is at least 1.5x chunk duration
        # to prevent single-chunk noise from breaking tones.
        safe_dropout = self.chunk_duration * 1.5
        if dropout_tolerance < safe_dropout:
            logger.warning(
                f"dropout_tolerance ({dropout_tolerance:.3f}s) is too low for "
                f"chunk_duration ({self.chunk_duration:.3f}s). "
                f"Increasing to {safe_dropout:.3f}s for stability."
            )
            dropout_tolerance = safe_dropout

        # Configuration
        self.min_tone_duration = min_tone_duration
        self.dropout_tolerance = dropout_tolerance
        self.frequency_tolerance = frequency_tolerance
        self.freq_smoothing = freq_smoothing
        self.dip_threshold = dip_threshold
        self.strong_signal_ratio = strong_signal_ratio
        self.coalesce_ratio = coalesce_ratio

        # State
        self.active_tones: List[ActiveTone] = []
        self.last_process_time = 0.0

        # Buffer for events to ensure chronological output
        self.pending_output: List[ToneEvent] = []

    def process(self, peaks: List[Peak], timestamp: float) -> List[AudioEvent]:
        """Process spectral peaks for a time slice and return completed events.

        This function should be called for every analyzed audio chunk.

        Args:
            peaks: List of significant spectral peaks detected by the DSP layer.
            timestamp: The end time of the current audio chunk in seconds.

        Returns:
            A list of completed `ToneEvent` objects. Note that events are only
            emitted *after* they have finished (and the dropout tolerance timer
            has expired), so there is inherent latency equal to `dropout_tolerance`.
        """
        # 1. Update active tones
        current_active_indices = set()

        for peak in peaks:
            matched = False
            for i, tone in enumerate(self.active_tones):
                if abs(peak.frequency - tone.frequency) < self.frequency_tolerance:
                    # 2. Track frequency history/smoothing
                    tone.frequency = (
                        1.0 - self.freq_smoothing
                    ) * tone.frequency + self.freq_smoothing * peak.frequency

                    # Upgrade: Instantaneous Dip Detection (Grandmaster feature)
                    # If magnitude drops by >40% compared to PREVIOUS chunk,
                    # we are likely entering the reverb tail.
                    magnitude_ratio = peak.magnitude / (
                        tone.last_magnitude if tone.last_magnitude > 0 else 1.0
                    )

                    if magnitude_ratio < self.dip_threshold:
                        # Significant dip - This is likely the end of the beep and start of reverb.
                        # We force a disconnect here so the beep duration isn't stretched.
                        matched = False
                        break

                    if peak.magnitude > tone.max_magnitude * self.strong_signal_ratio:
                        # Signal is still strong and consistent
                        tone.last_strong_time = timestamp

                    if peak.magnitude > tone.max_magnitude:
                        tone.max_magnitude = peak.magnitude

                    tone.last_magnitude = peak.magnitude  # Track for NEXT dip check
                    tone.last_seen_time = timestamp
                    tone.samples_count += 1
                    current_active_indices.add(i)
                    matched = True
                    break

            if not matched:
                # New potential tone
                new_tone = ActiveTone(
                    start_time=timestamp,
                    frequency=peak.frequency,
                    max_magnitude=peak.magnitude,
                    last_seen_time=timestamp,
                    last_strong_time=timestamp,
                    last_magnitude=peak.magnitude,
                    samples_count=1,
                )
                self.active_tones.append(new_tone)
                current_active_indices.add(len(self.active_tones) - 1)

        # 2. Check for ended tones
        active_tones_next: List[ActiveTone] = []
        new_events: List[ToneEvent] = []

        for i, tone in enumerate(self.active_tones):
            if i in current_active_indices:
                active_tones_next.append(tone)
            else:
                time_since_seen = timestamp - tone.last_seen_time

                if time_since_seen > self.dropout_tolerance:
                    # Tone ended - Use 'last_strong_time' for precision duration (Elite feature)
                    # This cuts off the reverb tail and restores the true pattern rhythm.
                    duration = (tone.last_strong_time - tone.start_time) + self.chunk_duration

                    # Safety check: ensure duration is at least one chunk
                    duration = max(self.chunk_duration, duration)

                    if duration >= self.min_tone_duration:
                        event = ToneEvent(
                            timestamp=tone.start_time,
                            duration=duration,
                            frequency=tone.frequency,
                            magnitude=tone.max_magnitude,
                            confidence=1.0,
                        )
                        new_events.append(event)
                        logger.debug(
                            f"Generated Tone: {event.frequency:.0f}Hz, {event.duration:.2f}s"
                        )
                else:
                    # Keep waiting (dropout tolerance)
                    active_tones_next.append(tone)

        self.active_tones = active_tones_next
        self.last_process_time = timestamp

        # 3. Add new events to pending output buffer
        if new_events:
            self.pending_output.extend(new_events)
            # Sort pending events by start time
            self.pending_output.sort(key=lambda e: e.timestamp)

        # 4. Safe Release Logic:
        # We can only release events that started BEFORE the oldest active tone's start time.
        # This guarantees that no future event will be generated with an EARLIER timestamp
        # than what we release now.

        ready_events: List[ToneEvent] = []

        if not self.active_tones:
            # No active tones -> Safe to release everything
            ready_events = self.pending_output
            self.pending_output = []
        else:
            # Find the oldest start time among active tones
            min_active_start = min(t.start_time for t in self.active_tones)

            # Release events that definitely happen before any potential new event
            # (Note: allowing a small margin for float equality)
            split_idx = 0
            for i, event in enumerate(self.pending_output):
                if event.timestamp < min_active_start:
                    split_idx = i + 1
                else:
                    break

            if split_idx > 0:
                ready_events = self.pending_output[:split_idx]
                self.pending_output = self.pending_output[split_idx:]

        # 5. Coalesce overlapping ready events
        if len(ready_events) > 1:
            coalesced_events = []

            if ready_events:
                current_event = ready_events[0]

                for next_event in ready_events[1:]:
                    # Check for overlap
                    current_end = current_event.timestamp + current_event.duration
                    next_start = next_event.timestamp

                    # If they overlap significantly (more than 50% of the shorter one)
                    overlap = max(
                        0, min(current_end, next_event.timestamp + next_event.duration) - next_start
                    )
                    min_dur = min(current_event.duration, next_event.duration)

                    if overlap > self.coalesce_ratio * min_dur:
                        # Overlap detected - coalescing
                        if next_event.duration > current_event.duration:
                            current_event = next_event
                    else:
                        coalesced_events.append(current_event)
                        current_event = next_event

                coalesced_events.append(current_event)
                ready_events = coalesced_events

        return ready_events
