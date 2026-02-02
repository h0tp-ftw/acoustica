#!/usr/bin/env python3
"""Example: Process audio without microphone capture.

This example shows how to feed audio data directly to the engine,
useful for:
- Processing audio files
- Custom audio sources
- Testing and simulation
"""

import sys
from pathlib import Path

import numpy as np

# Add src to path to allow running without installation
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from acoustic_engine import AudioConfig, Engine
from acoustic_engine.models import AlarmProfile, Range, Segment


def generate_tone(frequency: float, duration: float, sample_rate: int) -> np.ndarray:
    """Generate a synthetic tone."""
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    # Sine wave with envelope
    envelope = np.minimum(1.0, np.minimum(t / 0.01, (duration - t) / 0.01))
    signal = np.sin(2 * np.pi * frequency * t) * 0.5 * envelope
    # Convert to int16
    return (signal * 32767).astype(np.int16)


def generate_silence(duration: float, sample_rate: int) -> np.ndarray:
    """Generate silence."""
    return np.zeros(int(sample_rate * duration), dtype=np.int16)


def main():
    # Define a simple alarm profile programmatically
    profile = AlarmProfile(
        name="TestAlarm",
        segments=[
            Segment(
                type="tone",
                frequency=Range(2900, 3100),
                duration=Range(0.4, 0.6),
            ),
            Segment(
                type="silence",
                duration=Range(0.1, 0.3),
            ),
        ],
        confirmation_cycles=2,
    )

    audio_config = AudioConfig(sample_rate=44100, chunk_size=4096)

    detections = []

    def on_detection(name):
        detections.append(name)
        print(f"🚨 Detected: {name}")

    # Create engine
    engine = Engine(profiles=[profile], audio_config=audio_config, on_detection=on_detection)

    print("Generating synthetic alarm pattern...")

    # Generate a test pattern: Beep-Silence-Beep-Silence x 3 cycles
    chunks = []
    for cycle in range(3):
        # Tone
        tone = generate_tone(3000, 0.5, audio_config.sample_rate)
        chunks.append(tone)
        # Silence
        silence = generate_silence(0.2, audio_config.sample_rate)
        chunks.append(silence)

    # Combine and split into chunks
    full_audio = np.concatenate(chunks)

    print(f"Total audio length: {len(full_audio) / audio_config.sample_rate:.2f}s")
    print("Processing...")

    # Feed to engine chunk by chunk
    chunk_size = audio_config.chunk_size
    for i in range(0, len(full_audio) - chunk_size, chunk_size):
        chunk = full_audio[i : i + chunk_size]
        engine.process_chunk(chunk)

    print(f"\nDetections: {len(detections)}")
    if detections:
        print("✅ Alarm pattern successfully detected!")
    else:
        print("⚠️  No detections (may need more cycles)")


if __name__ == "__main__":
    main()
