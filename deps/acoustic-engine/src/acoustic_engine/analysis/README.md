# 🧠 Analysis Module

The `analysis` module contains the "intelligence" of the engine. It converts filtered frequency peaks into discrete tone events and matches them against complex rhythmic patterns.

## 🛠 Components

### `EventGenerator` (in `generator.py`)

Tracks the persistence and continuity of frequencies over time.

- **Peak Tracking**: Maintains state for multiple concurrent candidate tones.
- **Debouncing**: Ignores momentary spectral spikes. A tone must persist for `min_tone_duration` to be registered.
- **Bridge Gap Logic**: Handles minor audio dropouts (e.g., from packet loss or interference). If a tone disappears for less than `dropout_tolerance`, it is treated as a single continuous event.
- **Event Emission**: Emits `ToneEvent` objects with precise start times and durations.

### `WindowedMatcher` (in `windowed_matcher.py`)

The primary detection engine that replaces traditional state machines.

- **Non-Linear Matching**: Instead of waiting for beeps in a strict order, it look at a "window" of time. This allows it to detect patterns even if the audio starts mid-pattern or contains impulsive noise (like a door slamming) between beeps.
- **Scoring System**: Evaluates potential matches based on how many cycles are completed and how well they fit the profile's timing constraints.
- **Robustness**: Can "skip" over intermittent noise that doesn't fit the expected rhythm.

### `EventBuffer` (in `event_buffer.py`)

A circular time-indexed storage for events.

- **Historical Context**: Retains `ToneEvents` for a configurable duration (typically 10-60 seconds).
- **Efficient Querying**: Allows the `WindowedMatcher` to quickly retrieve events within a specific time range for analysis.

## 📋 usage

```python
from acoustic_engine.analysis.generator import EventGenerator
from acoustic_engine.analysis.windowed_matcher import WindowedMatcher
from acoustic_engine.config import EngineConfig

# Analysis requires an EngineConfig (for timing tolerances)
config = EngineConfig(min_tone_duration=0.05, dropout_tolerance=0.05)

# 1. Setup Generator
generator = EventGenerator(config)

# 2. Setup Matcher with a profile
matcher = WindowedMatcher(profiles=[my_profile])

# In the processing loop:
tones = generator.update(relevant_peaks) # Returns list of completed ToneEvents
for tone in tones:
    # Add to matchers
    matcher.add_event(tone)

# Check for matches every ~0.5s
matches = matcher.evaluate()
for match in matches:
    print(f"🚨 Detected {match.profile_name}!")
```

## ⚙️ Why "Windowed" Analysis?

Traditional sequential state machines are fragile. If a single beep is missed or a random noise is mistakenly identified as a beep, the state machine resets or fails. The `WindowedMatcher` looks at the "big picture," requiring only that a valid pattern _exists_ within the historical buffer, making it immune to many types of interference that break simpler detectors.
