"""Benchmark: Drone/Stationary Noise Rejection.

This benchmark tests the engine's ability to detect alarms in the presence of
loud, stationary "drone" noises (e.g., fans, motors, hums).

Hypothesis:
The Spectral Subtraction (Per-Bin Noise Profiling) feature should learn the
stationary profile of the drone noise and suppress it, allowing the pulsing
alarm to be detected even if the drone noise is significant or consumes
'peak slots' in the DSP top-k list.
"""

import logging
import sys
import time
from typing import List, Tuple

import numpy as np

# Adjust path to import engine
sys.path.append("src")
from acoustic_engine.config import EngineConfig
from acoustic_engine.engine import Engine
from acoustic_engine.models import AlarmProfile, Range, Segment

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("BenchmarkDrone")


def generate_drone_audio(
    duration_sec: float,
    sample_rate: int,
    drone_freqs: List[float],
    drone_amp: float = 0.5,
    alarm_freq: float = 3000.0,
    alarm_pattern: List[Tuple[float, float]] = None,  # (on_duration, off_duration)
) -> np.ndarray:
    """Generate audio with constant drone tones and a pulsing alarm."""
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    audio = np.zeros_like(t)

    # 1. Add Drone Tones (Constant)
    for f in drone_freqs:
        # Add random phase to make it realistic
        phase = np.random.random() * 2 * np.pi
        audio += drone_amp * np.sin(2 * np.pi * f * t + phase)

    # 2. Add Alarm (Pulsing)
    # Standard T3: 0.5s ON, 0.5s OFF, 0.5s ON, 0.5s OFF, 0.5s ON, 1.5s OFF
    if alarm_pattern is None:
        # T3 Pattern
        pattern = [(0.5, 0.5), (0.5, 0.5), (0.5, 1.5)]
    else:
        pattern = alarm_pattern

    # Generate full pattern sequence
    current_t = 1.0  # Start alarm after 1 second to let noise floor settle
    while current_t < duration_sec:
        for on_dur, off_dur in pattern:
            if current_t + on_dur > duration_sec:
                break

            # Add alarm tone
            # Alarm amplitude is 0.3 (quieter than individual drone tones!)
            # This forces the system to rely on suppression to see it in top-k
            idx_start = int(current_t * sample_rate)
            idx_end = int((current_t + on_dur) * sample_rate)

            # Simple sine for alarm
            segment_t = t[idx_start:idx_end]
            audio[idx_start:idx_end] += 0.3 * np.sin(2 * np.pi * alarm_freq * segment_t)

            current_t += on_dur + off_dur

    # Normalize to -1.0 to 1.0
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = audio / max_val

    # Convert to int16
    return (audio * 32767).astype(np.int16)


def run_benchmark():
    # 1. Create Profile
    profile = AlarmProfile(
        name="Smoke Alarm",
        segments=[
            Segment(type="tone", frequency=Range(2900, 3100), duration=Range(0.4, 0.6)),
            Segment(type="silence", duration=Range(0.4, 0.6)),
            Segment(type="tone", frequency=Range(2900, 3100), duration=Range(0.4, 0.6)),
            Segment(type="silence", duration=Range(0.4, 0.6)),
            Segment(type="tone", frequency=Range(2900, 3100), duration=Range(0.4, 0.6)),
            Segment(type="silence", duration=Range(1.3, 1.7)),  # Long Gap
        ],
    )

    # 2. Setup Engine
    # We use aggressive max_peaks=5 to simulate contention
    config = EngineConfig.standard()
    config.max_peaks = 5
    config.noise_learning_rate = 0.05  # Fast learning for benchmark speed
    config.min_magnitude = 2.0  # Lower threshold due to normalization scaling

    engine = Engine(
        profiles=[profile],
        engine_config=config,
        on_detection=lambda p: print(f"ALARM DETECTED: {p}"),
    )

    # 3. generate Audio
    # 5 Drone tones. If max_peaks=5, these 5 should fill the list.
    # If the alarm (6th tone) is quieter than them, it will be ignored by simple sorting
    # UNLESS the drone tones are suppressed by spectral subtraction.
    drone_freqs = [500, 1000, 1500, 2000, 2500]
    # Alarm is at 3000.
    # Drone amp is 0.5 each. Alarm amp is 0.3.
    # Without suppression, the top 5 peaks are the drone tones. Alarm is #6.

    duration = 15.0
    audio = generate_drone_audio(duration, 44100, drone_freqs, drone_amp=0.5, alarm_freq=3000.0)

    logger.info("Starting Benchmark: Drone Noise Suppression")
    logger.info("Detailed Config: 5 Loud Drones (0.5 amp) vs 1 Quiet Alarm (0.3 amp)")
    logger.info("Expectation: Alarm should be detected because drones are stationary.")

    chunk_size = config.chunk_size
    detected = False

    start_time = time.time()
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i : i + chunk_size]
        if len(chunk) < chunk_size:
            break

        if engine.process_chunk(chunk):
            detected = True
            logger.info(f"Success! Alarm detected at audio time {i / 44100:.2f}s")
            break

    end_time = time.time()

    if detected:
        logger.info("✅ PASSED: Spectral subtraction successfully suppressed drone noise.")
    else:
        logger.error("❌ FAILED: Alarm was hidden by drone noise.")
        # Optional: Print debug info if we could access internal state


if __name__ == "__main__":
    try:
        run_benchmark()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
