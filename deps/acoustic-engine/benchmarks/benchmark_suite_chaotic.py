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
        """Generate Chaotic Spectral Noise.

        This creates noise where different frequencies have different random loudness levels.
        It simulates a "colored" noise environment (like a room with specific hums,
        resonances, and quiet spots) rather than uniform white/pink noise.
        """
        num_samples = int(self.sample_rate * duration)

        # 1. Base: White Noise
        white = np.random.randn(num_samples)

        # 2. FFT
        spectrum = np.fft.rfft(white)
        n_bins = len(spectrum)

        # 3. Create Random Spectral Envelope
        # We generate random "key points" across the spectrum and interpolate them
        # to create a smooth-ish but chaotic curve.
        num_control_points = 64  # How "wavy" the spectrum is

        # Frequencies for control points (logarithmic spacing looks more natural, but linear is fine for chaos)
        # Let's use linear for true randomness across the board
        indices = np.linspace(0, n_bins - 1, num_control_points)

        # Random gains for these points (0.0 to 1.0)
        # Squared to emphasize peaks vs valleys
        random_gains = np.random.uniform(0.0, 1.0, num_control_points) ** 2

        # Interpolate to create full envelope
        envelope = np.interp(np.arange(n_bins), indices, random_gains)

        # 4. Apply Envelope
        colored_spectrum = spectrum * envelope

        # 5. Inverse FFT
        chaotic_noise = np.fft.irfft(colored_spectrum)

        # 6. Normalize
        # Ensure the peak amplitude matches requested level
        if len(chaotic_noise) > 0:
            # We want reasonable RMS power, not just peak normalization
            # But for simplicity in this benchmark, peak norm to 'amplitude' is safe
            max_val = np.max(np.abs(chaotic_noise))
            if max_val > 0:
                # Scale so the loudest frequency peak hits the limit
                chaotic_noise = chaotic_noise / max_val * amplitude

        return chaotic_noise[:num_samples]

    def mix_noise(self, audio: np.ndarray, noise_level: float) -> np.ndarray:
        if noise_level <= 0:
            return audio

        noise = self.generate_noise(len(audio) / self.sample_rate, amplitude=noise_level)
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
    print("🚀 ACOUSTIC ENGINE BENCHMARK")
    print("=" * 70)

    # Setup
    temp_dir = tempfile.mkdtemp()
    gen = AudioGenerator()

    # Define scenarios
    scenarios = [
        ("Standard T3 (Stable)", generate_t3_pattern, create_t3_profile),
        ("Fast T4 (High Res)", generate_fast_t4_pattern, create_fast_t4_profile),
    ]

    noise_levels = [0.0, 0.1, 0.25, 0.5, 0.8]

    for name, audio_func, profile_func in scenarios:
        print(f"\nBenchmark Scenario: {name}")
        print("-" * 40)

        # Create Profile
        profile_path = os.path.join(temp_dir, "profile.yaml")
        profile_func(profile_path)

        # Generate Audio
        raw_audio = audio_func(gen)

        for noise in noise_levels:
            # Create Noisy Audio File
            wav_path = os.path.join(temp_dir, f"test_{noise}.wav")
            mixed_audio = gen.mix_noise(raw_audio, noise)
            gen.create_wav_file(wav_path, mixed_audio)

            # Run Test
            display = Display(verbose=False)

            # Determine resolution mode
            high_res = "High Res" in name

            runner = TestRunner(
                profile_path=Path(profile_path),
                verbose=False,
                display=display,
                high_resolution=high_res,
            )

            runner.run_file(Path(wav_path))

            detected = len(runner.results.detections) > 0
            status = "✅ PASS" if detected else "❌ FAIL"

            # Calculate SNR (approximate)
            # Signal amp is 0.5, Noise amp is 'noise'
            # SNR = 20 * log10(Signal/Noise)
            if noise > 0:
                snr = 20 * np.log10(0.5 / noise)
                snr_str = f"SNR {snr:5.1f}dB"
            else:
                snr_str = "Clean     "

            print(
                f"  Noise Level {noise * 100:3.0f}% ({snr_str}) | {status} | Matches: {len(runner.results.detections)}"
            )

            # Cleanup wav
            os.remove(wav_path)

    # Cleanup
    import shutil

    shutil.rmtree(temp_dir)
    print("\nBenchmark Complete.")


if __name__ == "__main__":
    run_benchmark()
