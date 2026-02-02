#!/usr/bin/env python3
"""Benchmark Suite for Acoustic Alarm Engine.

Generates synthetic alarm patterns and tests detection robustness
against increasing noise levels.
"""

import logging
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from acoustic_engine.tester.display import Display
from acoustic_engine.tester.runner import TestRunner

# Configure logging to only show critical errors during benchmark to keep output clean
logging.basicConfig(level=logging.ERROR)


class AudioGenerator:
    """Generates synthetic audio files."""

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate

    def generate_tone(
        self, frequency: float, duration: float, amplitude: float = 0.5
    ) -> np.ndarray:
        t = np.linspace(0, duration, int(self.sample_rate * duration), False)
        # Generate sine wave
        tone = np.sin(2 * np.pi * frequency * t) * amplitude
        return tone

    def generate_silence(self, duration: float) -> np.ndarray:
        return np.zeros(int(self.sample_rate * duration))

    def generate_noise(self, duration: float, amplitude: float = 0.5) -> np.ndarray:
        # white noise
        return np.random.uniform(-amplitude, amplitude, int(self.sample_rate * duration))

    def mix_noise(self, audio: np.ndarray, noise_level: float) -> np.ndarray:
        if noise_level <= 0:
            return audio

        noise = np.random.uniform(-noise_level, noise_level, len(audio))
        return audio + noise

    def create_wav_file(self, filename: str, audio: np.ndarray):
        # Convert to 16-bit PCM
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            normalized = audio / max_val * 0.9  # Avoid clipping
        else:
            normalized = audio

        int_audio = (normalized * 32767).astype(np.int16)
        wavfile.write(filename, self.sample_rate, int_audio)


def generate_t3_pattern(generator: AudioGenerator, frequency: float = 3000) -> np.ndarray:
    """Generates a T3 pattern (3 beeps)."""
    # T3: 0.5s ON, 0.5s OFF, 0.5s ON, 0.5s OFF, 0.5s ON, 1.5s OFF
    tone = generator.generate_tone(frequency, 0.5)
    short_silence = generator.generate_silence(0.5)
    long_silence = generator.generate_silence(1.5)

    pattern = np.concatenate([tone, short_silence, tone, short_silence, tone, long_silence])

    # Repeat pattern 3 times
    return np.concatenate([pattern, pattern, pattern])


def generate_fast_t4_pattern(generator: AudioGenerator, frequency: float = 3000) -> np.ndarray:
    """Generates a fast T4 pattern (4 short beeps)."""
    # Fast T4: 0.1s ON, 0.1s OFF (x4) then 2.0s OFF
    tone = generator.generate_tone(frequency, 0.05)  # Very fast 50ms beep
    silence = generator.generate_silence(0.05)  # Very fast 50ms gap
    long_silence = generator.generate_silence(2.0)

    unit = np.concatenate([tone, silence])
    # 4 beeps
    pattern = np.concatenate([unit, unit, unit, unit, long_silence])

    # Repeat pattern 3 times
    return np.concatenate([pattern, pattern, pattern])


def generate_wrong_freq_t3(generator: AudioGenerator, frequency: float = 1500) -> np.ndarray:
    """Generates T3 pattern but at WRONG frequency (1500Hz vs 3000Hz)."""
    # Same timing, different pitch
    return generate_t3_pattern(generator, frequency=1500)


def generate_t3_custom_timing(
    generator: AudioGenerator,
    frequency: float = 3000,
    beep_dur: float = 0.5,
    gap_dur: float = 0.5,
    long_gap_dur: float = 1.5,
) -> np.ndarray:
    """Generates a T3 pattern with custom timing."""
    tone = generator.generate_tone(frequency, beep_dur)
    short_silence = generator.generate_silence(gap_dur)
    long_silence = generator.generate_silence(long_gap_dur)

    pattern = np.concatenate([tone, short_silence, tone, short_silence, tone, long_silence])

    # Repeat pattern 3 times
    return np.concatenate([pattern, pattern, pattern])


def create_t3_profile(filename: str):
    profile_content = """
name: "Benchmark T3"
segments:
  - type: tone
    frequency:
      min: 2900
      max: 3100
    duration:
      min: 0.4
      max: 0.6
  - type: silence
    duration:
      min: 0.4
      max: 0.6
  - type: tone
    frequency:
      min: 2900
      max: 3100
    duration:
      min: 0.4
      max: 0.6
  - type: silence
    duration:
      min: 0.4
      max: 0.6
  - type: tone
    frequency:
      min: 2900
      max: 3100
    duration:
      min: 0.4
      max: 0.6
  - type: silence
    duration:
      min: 1.3
      max: 1.7
confirmation_cycles: 2
"""
    with open(filename, "w") as f:
        f.write(profile_content)


def create_fast_t4_profile(filename: str):
    profile_content = """
name: "Benchmark Fast T4"
resolution:
    min_tone_duration: 0.03
    dropout_tolerance: 0.03
segments:
  - type: tone
    frequency:
      min: 2900
      max: 3100
    duration:
      min: 0.04
      max: 0.08
  - type: silence
    duration:
      min: 0.04
      max: 0.08
  - type: tone
    frequency:
      min: 2900
      max: 3100
    duration:
      min: 0.04
      max: 0.08
  - type: silence
    duration:
      min: 0.04
      max: 0.08
  - type: tone
    frequency:
      min: 2900
      max: 3100
    duration:
      min: 0.04
      max: 0.08
  - type: silence
    duration:
      min: 0.04
      max: 0.08
  - type: tone
    frequency:
      min: 2900
      max: 3100
    duration:
      min: 0.04
      max: 0.08
  - type: silence
    duration:
      min: 1.5
      max: 2.5
confirmation_cycles: 2
"""
    with open(filename, "w") as f:
        f.write(profile_content)


def run_benchmark():
    print("=" * 70)
    print("🛡️ SPECIFICITY BENCHMARK (False Positive Test)")
    print("=" * 70)

    # Setup
    temp_dir = tempfile.mkdtemp()
    gen = AudioGenerator()

    # Define scenarios
    # Format: (Name, AudioFunc, ProfileFunc, ExpectedResult)
    # ExpectedResult: True if valid alarm, False if should be rejected
    scenarios = [
        ("Control: Valid T3", generate_t3_pattern, create_t3_profile, True),
        ("Negative: Wrong Freq (1500Hz)", generate_wrong_freq_t3, create_t3_profile, False),
        (
            "Negative: Too Short (0.2s)",
            lambda g: generate_t3_custom_timing(g, beep_dur=0.2),
            create_t3_profile,
            False,
        ),
        (
            "Negative: Too Short (0.3s)",
            lambda g: generate_t3_custom_timing(g, beep_dur=0.3),
            create_t3_profile,
            False,
        ),
        (
            "Negative: Too Long (1.0s)",
            lambda g: generate_t3_custom_timing(g, beep_dur=1.0),
            create_t3_profile,
            False,
        ),
        (
            "Negative: Wrong Gaps (2.0s)",
            lambda g: generate_t3_custom_timing(g, gap_dur=2.0),
            create_t3_profile,
            False,
        ),
        ("Negative: Pure Noise", lambda g: g.generate_noise(5.0), create_t3_profile, False),
    ]

    # We only test clean audio + one noise level for specificity
    noise_levels = [0.0, 0.25]

    for name, audio_func, profile_func, expect_match in scenarios:
        print(f"\nScenario: {name}")
        print("-" * 40)

        # Create Profile
        profile_path = os.path.join(temp_dir, "profile.yaml")
        profile_func(profile_path)

        # Generate Audio
        if name == "Negative: Pure Noise":
            raw_audio = audio_func(gen)
        else:
            raw_audio = audio_func(gen)

        for noise in noise_levels:
            # Create Noisy Audio File
            wav_path = os.path.join(temp_dir, f"test_{noise}.wav")
            mixed_audio = gen.mix_noise(raw_audio, noise)
            gen.create_wav_file(wav_path, mixed_audio)

            # Run Test
            display = Display(verbose=False)
            runner = TestRunner(profile_path=Path(profile_path), verbose=False, display=display)

            runner.run_file(Path(wav_path))

            match_count = len(runner.results.detections)
            detected = match_count > 0

            # Logic:
            # If expect_match=True, we WANT detections.
            # If expect_match=False, we WANT NO detections.

            if expect_match:
                status = "✅ PASS (Detected)" if detected else "❌ FAIL (False Negative)"
            else:
                status = "✅ PASS (Rejected)" if not detected else "❌ FAIL (False Positive)"

            # Calculate SNR
            if noise > 0:
                snr = 20 * np.log10(0.5 / noise)
                snr_str = f"SNR {snr:5.1f}dB"
            else:
                snr_str = "Clean     "

            print(f"  Noise {noise * 100:3.0f}% ({snr_str}) | {status} | Matches: {match_count}")

            # Cleanup wav
            os.remove(wav_path)

    # Cleanup
    import shutil

    shutil.rmtree(temp_dir)
    print("\nSpecificity Benchmark Complete.")


if __name__ == "__main__":
    run_benchmark()
