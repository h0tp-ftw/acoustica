#!/usr/bin/env python3
"""Advanced Edge-Case Benchmarks for Acoustic Alarm Engine.

Tests complex environmental challenges:
1. Reverb/Echo (Signal Smearing)
2. Impulsive Noise (Transient Striking)
3. Frequency Drifts (Sweeping Tones)
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np

# Add current dir and src to path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir.parent / "src"))

from benchmark_suite import AudioGenerator, create_t3_profile

from acoustic_engine.tester.display import Display
from acoustic_engine.tester.runner import TestRunner


class AdvancedAudioGenerator(AudioGenerator):
    """Generates audio with physical distortions like Reverb."""

    def apply_reverb(self, audio: np.ndarray, decay: float = 0.3, delay_ms: int = 50) -> np.ndarray:
        """Simulates simple recursive echo/reverb."""
        delay_samples = int(self.sample_rate * (delay_ms / 1000.0))
        output = audio.copy()

        # Simple feedback loop reverb
        for i in range(delay_samples, len(output)):
            output[i] += output[i - delay_samples] * decay

        # Normalize to prevent clipping
        max_val = np.max(np.abs(output))
        if max_val > 1.0:
            output /= max_val

        return output

    def generate_swept_t3(
        self, start_freq: float, end_freq: float, duration: float = 0.5
    ) -> np.ndarray:
        """Generates T3 beeps that drift in frequency."""

        # This is more complex; we'll implement for one cycle
        # For simplicity, we'll just use a chirp for each beep
        def chirp(f0, f1, t_dur):
            t = np.linspace(0, t_dur, int(self.sample_rate * t_dur), False)
            # Linear frequency sweep
            phase = 2 * np.pi * (f0 * t + (f1 - f0) * t**2 / (2 * t_dur))
            return np.sin(phase) * 0.5

        beep1 = chirp(start_freq, start_freq + (end_freq - start_freq) * 0.3, 0.5)
        beep2 = chirp(
            start_freq + (end_freq - start_freq) * 0.4,
            start_freq + (end_freq - start_freq) * 0.7,
            0.5,
        )
        beep3 = chirp(start_freq + (end_freq - start_freq) * 0.7, end_freq, 0.5)

        silence = self.generate_silence(0.5)
        long_silence = self.generate_silence(1.5)

        pattern = np.concatenate([beep1, silence, beep2, silence, beep3, long_silence])
        return np.concatenate([pattern, pattern, pattern])

    def generate_collision(
        self, target_freq: float = 3000, distractor_freq: float = 2000
    ) -> np.ndarray:
        """Generates two overlapping alarm patterns."""
        # Target: T3 at 3000Hz
        target = self.generate_tone(target_freq, 0.5)
        sil_target = self.generate_silence(0.5)
        long_sil_target = self.generate_silence(1.5)
        target_pat = np.concatenate(
            [target, sil_target, target, sil_target, target, long_sil_target]
        )
        target_audio = np.concatenate([target_pat, target_pat])

        # Distractor: Fast T4 at 2000Hz
        dist = self.generate_tone(distractor_freq, 0.1)
        sil_dist = self.generate_silence(0.1)
        long_sil_dist = self.generate_silence(2.0)
        dist_pat = np.concatenate(
            [dist, sil_dist, dist, sil_dist, dist, sil_dist, dist, long_sil_dist]
        )
        # Repeat 4 times to ensure audio is long enough (10s+)
        dist_audio = np.concatenate(
            [self.generate_silence(0.3), dist_pat, dist_pat, dist_pat, dist_pat]
        )

        # Mix them (truncate to shortest - target is 8s, dist is 10s+)
        min_len = min(len(target_audio), len(dist_audio))
        return target_audio[:min_len] + dist_audio[:min_len]


def create_t3_profile_wide(filename: str):
    profile_content = """
name: "Wide T3"
segments:
  - type: tone
    frequency:
      min: 2800
      max: 3400
    duration:
      min: 0.4
      max: 0.6
  - type: silence
    duration:
      min: 0.4
      max: 0.6
  - type: tone
    frequency:
      min: 2800
      max: 3400
    duration:
      min: 0.4
      max: 0.6
  - type: silence
    duration:
      min: 0.4
      max: 0.6
  - type: tone
    frequency:
      min: 2800
      max: 3400
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


def run_edge_benchmarks():
    print("=" * 70)
    print("🧪 ADVANCED EDGE-CASE BENCHMARK (UPGRADED ENGINE)")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp()
    gen = AdvancedAudioGenerator()

    # 1. THE REVERB TEST
    print("\n[Case 1] Echo/Reverb Challenge (Smearing Gaps)")
    print("-" * 50)

    raw_t3 = gen.generate_tone(3000, 0.5)
    silence = gen.generate_silence(0.5)
    long_silence = gen.generate_silence(1.5)
    t3_pattern = np.concatenate([raw_t3, silence, raw_t3, silence, raw_t3, long_silence])
    t3_audio = np.concatenate([t3_pattern, t3_pattern])

    # Test with increasing reverb tail
    for decay in [0.3, 0.5, 0.7, 0.85]:
        wav_path = os.path.join(temp_dir, f"reverb_{decay}.wav")
        distorted = gen.apply_reverb(t3_audio, decay=decay)
        gen.create_wav_file(wav_path, distorted)

        profile_path = os.path.join(temp_dir, "profile.yaml")
        create_t3_profile(profile_path)

        runner = TestRunner(
            profile_path=Path(profile_path), verbose=False, display=Display(verbose=False)
        )
        runner.run_file(Path(wav_path))

        status = "✅ PASS" if len(runner.results.detections) > 0 else "❌ FAIL (Gaps Smeared)"
        print(
            f"  Reverb Decay {decay * 100:2.0f}% | {status} | Matches: {len(runner.results.detections)}"
        )

    # 2. THE FREQUENCY DRIFT TEST
    print("\n[Case 2] Frequency Drift Challenge (The Dying Piezo)")
    print("-" * 50)
    # Drift from 3000Hz to 3200Hz across the pattern
    wav_path_drift = os.path.join(temp_dir, "drift.wav")
    drifted = gen.generate_swept_t3(3000, 3200)
    gen.create_wav_file(wav_path_drift, drifted)

    # Use wide profile for drift
    profile_path_wide = os.path.join(temp_dir, "profile_wide.yaml")
    create_t3_profile_wide(profile_path_wide)

    runner_drift = TestRunner(
        profile_path=Path(profile_path_wide), verbose=False, display=Display(verbose=False)
    )
    runner_drift.run_file(Path(wav_path_drift))
    status_drift = (
        "✅ PASS" if len(runner_drift.results.detections) > 0 else "❌ FAIL (Frequency Lost)"
    )
    print(
        f"  Drift 3000->3200Hz | {status_drift} | Matches: {len(runner_drift.results.detections)}"
    )

    # 3. THE COLLISION TEST
    print("\n[Case 3] Target Collision Challenge (Two Alarms)")
    print("-" * 50)
    wav_path_coll = os.path.join(temp_dir, "collision.wav")
    collision = gen.generate_collision()
    gen.create_wav_file(wav_path_coll, collision)

    runner_coll = TestRunner(
        profile_path=Path(profile_path), verbose=False, display=Display(verbose=False)
    )
    runner_coll.run_file(Path(wav_path_coll))
    status_coll = "✅ PASS" if len(runner_coll.results.detections) > 0 else "❌ FAIL (Overwhelmed)"
    print(
        f"  T3 (3000Hz) vs T4 (2000Hz) | {status_coll} | Matches: {len(runner_coll.results.detections)}"
    )

    # Cleanup
    import shutil

    shutil.rmtree(temp_dir)


if __name__ == "__main__":
    run_edge_benchmarks()
