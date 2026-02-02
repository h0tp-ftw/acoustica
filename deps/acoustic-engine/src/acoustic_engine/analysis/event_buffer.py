"""Circular buffer for storing recent audio events for windowed analysis."""

from dataclasses import dataclass, field
from typing import List, Optional

from ..events import ToneEvent


@dataclass
class EventBuffer:
    """Stores recent audio events for windowed pattern matching.

    Maintains a time-ordered list of events, automatically pruning
    events older than max_duration.
    """

    max_duration: float = 30.0  # Keep events from last 30s
    _events: List[ToneEvent] = field(default_factory=list)

    def add(self, event: ToneEvent) -> None:
        """Add an event to the buffer.

        Events are assumed to arrive roughly in order. The buffer
        automatically prunes old events.

        Args:
            event: ToneEvent to add
        """
        self._events.append(event)

        # Prune old events (keep those within max_duration of latest)
        if self._events:
            latest_time = max(e.timestamp for e in self._events)
            cutoff = latest_time - self.max_duration
            self._events = [e for e in self._events if e.timestamp >= cutoff]

    def get_window(self, end_time: float, window_duration: float) -> List[ToneEvent]:
        """Get all events within a time window.

        Args:
            end_time: End of the window (usually current time)
            window_duration: How far back to look

        Returns:
            List of events within [end_time - window_duration, end_time]
        """
        start_time = end_time - window_duration
        return [e for e in self._events if start_time <= e.timestamp <= end_time]

    def get_events_in_range(
        self,
        start_time: float,
        end_time: float,
        freq_min: Optional[float] = None,
        freq_max: Optional[float] = None,
    ) -> List[ToneEvent]:
        """Get events in a time range, optionally filtered by frequency.

        Args:
            start_time: Start of range
            end_time: End of range
            freq_min: Optional minimum frequency filter
            freq_max: Optional maximum frequency filter

        Returns:
            Filtered list of events
        """
        events = [e for e in self._events if start_time <= e.timestamp <= end_time]

        if freq_min is not None and freq_max is not None:
            events = [e for e in events if freq_min <= e.frequency <= freq_max]

        return sorted(events, key=lambda e: e.timestamp)

    def clear(self) -> None:
        """Clear all events from the buffer."""
        self._events.clear()

    @property
    def events(self) -> List[ToneEvent]:
        """Get all events in the buffer (read-only)."""
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)
