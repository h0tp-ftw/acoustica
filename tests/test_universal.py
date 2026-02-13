"""
Test script for verifying Universal Alarm Engine.
Generates synthetic audio patterns to test matching logic.
"""

import numpy as np
import logging
from detector.detector import PatternDetector
from acoustic_alarm_engine.models import AlarmProfile, Segment, Range

# Configure logging to stdout
logging.basicConfig(level=logging.DEBUG, format="%(message)s")


def generate_tone(sample_rate, duration, frequency, amplitude=0.5):
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    return amplitude * np.sin(2 * np.pi * frequency * t)


def generate_silence(sample_rate, duration):
    return np.zeros(int(sample_rate * duration))


def run_test():
    SAMPLE_RATE = 44100
    CHUNK_SIZE = 4096

    print("--- Defining Universal Profile (Complex Siren) ---")
    # Pattern: 1kHz (0.5s) -> Silence (0.2s) -> 2kHz (0.5s) -> Silence (1.0s)
    # 2 Cycles required

    profile = AlarmProfile(
        name="ComplexSiren",
        confirmation_cycles=2,
        segments=[
            Segment(type="tone", frequency=Range(900, 1100), duration=Range(0.4, 0.6)),
            Segment(type="silence", duration=Range(0.1, 0.3)),
            Segment(type="tone", frequency=Range(1900, 2100), duration=Range(0.4, 0.6)),
            Segment(type="silence", duration=Range(0.8, 1.2)),
        ],
    )

    detector = PatternDetector(profile, SAMPLE_RATE, CHUNK_SIZE)

    print("\n--- Generating Audio Stream ---")
    audio_stream = np.array([], dtype=np.float32)

    # Cycle 1 (Valid)
    audio_stream = np.concatenate(
        [
            audio_stream,
            generate_tone(SAMPLE_RATE, 0.5, 1000),  # 1khz
            generate_silence(SAMPLE_RATE, 0.2),  # Gap
            generate_tone(SAMPLE_RATE, 0.5, 2000),  # 2khz
            generate_silence(SAMPLE_RATE, 1.0),  # Long Gap
        ]
    )

    # Cycle 2 (Valid)
    audio_stream = np.concatenate(
        [
            audio_stream,
            generate_tone(SAMPLE_RATE, 0.5, 1000),
            generate_silence(SAMPLE_RATE, 0.2),
            generate_tone(SAMPLE_RATE, 0.5, 2000),
            generate_silence(SAMPLE_RATE, 1.0),
        ]
    )

    # Cycle 3 (Start just to flush Cycle 2 final silence)
    audio_stream = np.concatenate(
        [
            audio_stream,
            generate_tone(SAMPLE_RATE, 0.5, 1000),
            generate_silence(SAMPLE_RATE, 1.0),  # OFFICIALLY END THE TONE
        ]
    )

    print(f"Total Audio Duration: {len(audio_stream) / SAMPLE_RATE:.2f}s")

    # Process in Chunks
    print("\n--- Processing ---")

    # Convert to int16 range for detector (it expects raw audio scaling)
    # The new DSP divides by 32768.0, so we should scale our 0.5 amplitude to 16384
    audio_int16 = (audio_stream * 32767).astype(np.int16)

    detected_count = 0
    for i in range(0, len(audio_int16), CHUNK_SIZE):
        chunk = audio_int16[i : i + CHUNK_SIZE]
        if len(chunk) < CHUNK_SIZE:
            break

        if detector.process(chunk):
            detected_count += 1

    print(f"\n--- Result: Detected {detected_count} times ---")
    if detected_count > 0:
        print("✅ SUCCESS: Alarm Detected")
    else:
        print("❌ FAILURE: No Detection")


if __name__ == "__main__":
    run_test()
