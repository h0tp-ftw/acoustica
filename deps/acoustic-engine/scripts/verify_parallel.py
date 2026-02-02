import logging
import sys
import wave
from pathlib import Path

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from acoustic_engine.parallel_engine import ParallelEngine
from acoustic_engine.profiles import load_profiles_from_yaml

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("acoustic_engine").setLevel(logging.DEBUG)
logger = logging.getLogger("ParallelVerifier")


def load_audio(path):
    """Load audio file as numpy array using standard wave module."""
    if not str(path).endswith(".wav"):
        raise ValueError("Please use .wav file.")

    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        audio_data = wf.readframes(n_frames)

        if sampwidth == 2:
            dtype = np.int16
        else:
            raise ValueError("Only 16-bit WAV supported")

        arr = np.frombuffer(audio_data, dtype=dtype).astype(np.float32)
        arr = arr / 32768.0  # Normalize

        if n_channels > 1:
            arr = arr.reshape(-1, n_channels)
            arr = arr[:, 0]

        return arr


def run_test():
    print("=" * 60)
    print("🧪 VERIFYING PARALLEL PIPELINES (REAL AUDIO)")
    print("=" * 60)

    # 1. Load Profiles
    smoke_profile = load_profiles_from_yaml("test_profile.yaml")[0]
    co_profile = load_profiles_from_yaml("CO_Sensor_profile.yaml")[0]

    print(f"Loaded Profile 1: {smoke_profile.name}")
    print(f"Loaded Profile 2: {co_profile.name}")

    # 2. Initialize Parallel Engine
    print("\nInitializing Parallel Engine...")
    engine = ParallelEngine(
        profiles=[smoke_profile, co_profile],
        on_detection=lambda p: print(f"  🔔 DETECTION CALLBACK: {p}"),
    )

    # 3. Process Full Audio
    print("\n--- Processing real_smoke_co_alarm.wav ---")
    audio = load_audio("real_smoke_co_alarm.wav")
    print(f"Loaded {len(audio)} samples ({len(audio) / 44100:.2f}s).")

    chunk_size = 1024
    total_chunks = len(audio) // chunk_size
    detections = []

    engine.on_match = lambda m: detections.append(f"{m.profile_name} @ {m.timestamp:.2f}s")

    for i in range(total_chunks):
        chunk = audio[i * chunk_size : (i + 1) * chunk_size]
        engine.process_chunk(chunk)

    print(f"\nResults ({len(detections)} matches):")
    for d in detections:
        print(f"  - {d}")

    # 4. Verify Both Detected
    smoke_detected = any("TestAlarm" in d for d in detections)
    co_detected = any("CO Sensor" in d for d in detections)

    if smoke_detected:
        print("✅ Smoke Alarm DETECTED")
    else:
        print("❌ Smoke Alarm NOT DETECTED")

    if co_detected:
        print("✅ CO Alarm DETECTED")
    else:
        print("❌ CO Alarm NOT DETECTED")

    if smoke_detected and co_detected:
        print("\n🏆 FINAL VERDICT: PARALLEL ARCHITECTURE SUCCESS")
    else:
        print("\n💥 FINAL VERDICT: PARTIAL FAILURE")


if __name__ == "__main__":
    run_test()
