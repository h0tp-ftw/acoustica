import os
import threading
import time

import numpy as np
import psutil

from acoustic_engine import AudioConfig, Engine
from acoustic_engine.profiles import load_profiles_from_yaml


def get_process_memory():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB


def benchmark():
    print("Starting Benchmark...")

    # 1. Baseline Memory
    baseline_mem = get_process_memory()
    print(f"Baseline Memory: {baseline_mem:.2f} MB")

    # 2. Load Profile & Init Engine
    start_time = time.time()
    # Assuming profile exists, otherwise create a dummy one
    profile_path = "profiles/smoke_alarm.yaml"
    if not os.path.exists(profile_path):
        # Fallback to creating a dummy profile string or using another path
        print(f"Warning: {profile_path} not found. Creating temporary profile.")
        with open("temp_profile.yaml", "w") as f:
            f.write("""
name: "BenchmarkAlarm"
segments:
  - type: tone
    frequency: { min: 3000, max: 3200 }
    duration: { min: 0.5, max: 0.5 }
  - type: silence
    duration: { min: 0.5, max: 0.5 }
""")
        profile_path = "temp_profile.yaml"

    profiles = load_profiles_from_yaml(profile_path)
    audio_config = AudioConfig(sample_rate=16000, chunk_size=1024)
    engine = Engine(profiles=profiles, audio_config=audio_config)

    init_time = (time.time() - start_time) * 1000
    loaded_mem = get_process_memory()
    print(f"Engine Initialized in: {init_time:.2f} ms")
    print(f"Loaded Memory: {loaded_mem:.2f} MB (Delta: {loaded_mem - baseline_mem:.2f} MB)")

    # 3. Processing Benchmark
    # Generate 60 seconds of silence + noise
    duration_sec = 60
    sample_rate = 16000
    chunk_size = 1024
    total_chunks = int(duration_sec * sample_rate / chunk_size)

    # Synthetic audio: White noise + Tone
    audio_data = np.random.normal(0, 0.01, size=chunk_size).astype(np.float32)

    print(f"Processing {duration_sec}s of audio...")
    process_start = time.time()

    cpu_usages = []

    # Simple CPU monitor thread
    monitor_running = True

    def monitor_cpu():
        p = psutil.Process()
        while monitor_running:
            cpu_usages.append(p.cpu_percent(interval=0.1))

    t = threading.Thread(target=monitor_cpu)
    t.start()

    for _ in range(total_chunks):
        engine.process_chunk(audio_data)

    process_end = time.time()
    monitor_running = False
    t.join()

    total_time = process_end - process_start
    realtime_factor = total_time / duration_sec
    avg_cpu = sum(cpu_usages) / len(cpu_usages) if cpu_usages else 0
    final_mem = get_process_memory()

    print("-" * 30)
    print(f"Processing Time: {total_time:.2f} s")
    print(f"Real-time Factor: {realtime_factor:.4f}x (Lower is better, <1.0 is realtime)")
    print(f"Average CPU Usage (Single Core): {avg_cpu:.1f}%")
    print(f"Peak Memory: {final_mem:.2f} MB")
    print("-" * 30)

    # Cleanup temp
    if profile_path == "temp_profile.yaml":
        os.remove("temp_profile.yaml")


if __name__ == "__main__":
    benchmark()
