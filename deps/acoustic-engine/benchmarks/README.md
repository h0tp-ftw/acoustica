# 🧪 Acoustic Alarm Engine Benchmarks

This directory contains a suite of rigorous tests designed to verify the engine's performance in varied, challenging environments.

## 🏃 Running Benchmarks

Run all benchmarks (this may take several minutes):

```bash
python3 benchmarks/benchmark_suite.py
python3 benchmarks/benchmark_suite_drone.py
python3 benchmarks/benchmark_suite_dynamic.py
python3 benchmarks/benchmark_suite_specificity.py
python3 benchmarks/benchmark_suite_edge_cases.py
```

## 📊 Benchmark Suites

### 1. Standard Regression (`benchmark_suite.py`)

Tests the core detection logic against increasing levels of random white noise.

- **Scenarios**: Standard T3 (Smoke), Fast T4 (CO).
- **Goal**: Verify basic functionality remains intact.

### 2. Drone Noise / Spectral Subtraction (`benchmark_suite_drone.py`)

Tests the engine's ability to ignore loud, stationary noise sources like fans, motors, or HVAC systems.

- **Mechanism**: Generates 5 loud "drone" tones (50% vol) and mixes them with a quiet alarm (30% vol).
- **Success Criteria**: The engine must "learn" the drone tones are background noise (via Spectral Subtraction) and detect the alarm appearing _underneath_ them.

### 3. Dynamic "Party" Noise (`benchmark_suite_dynamic.py`)

Tests robustness in non-stationary, chaotic environments (e.g., a living room with TV, music, and conversation).

- **Noise Types**:
  - **Babble**: Multiple overlapping speech-like bands shifting frequency every 200ms.
  - **Clatter**: High-frequency transient spikes (dishes, keys).
- **Success Criteria**: Detect alarm even when SNR is negative (Noise > Alarm).

### 4. Specificity / Negative Controls (`benchmark_suite_specificity.py`)

**CRITICAL**: This suite ensures the engine does NOT trigger on false positives. It feeds the engine "imposter" sounds.

- **Imposter Sounds**:
  - Wrong Frequency (1500Hz vs 3000Hz)
  - Wrong Timing (0.2s beeps vs 0.5s)
  - Wrong Rhythm (2.0s gaps vs 0.5s)
  - Pure Noise
- **Success Criteria**: The engine must **REJECT** all of these sounds (0 matches).

### 5. Edge Cases (`benchmark_suite_edge_cases.py`)

Tests extreme physical acoustic challenges.

- **Reverb**: Adds 30-85% reverb decay to simulate large warehouses.
- **Frequency Drift**: Simulates a dying battery buzzer drifting from 3000Hz to 3200Hz.
- **Collision**: (Currently Known Failure) Simulates two different alarms sounding simultaneously.

## 🛠 How It Works

Each benchmark script:

1.  **Generates Synthetic Audio**: Uses `numpy` to create mathematically perfect signals mixed with calculated noise.
2.  **Generates Temporary Profiles**: Creates a YAML profile specifically for that test (to ensure test isolation).
3.  **Runs the Engine**: Feeds the generated WAV file into `TestRunner`.
4.  **Asserts Results**: Checks if `len(detections) > 0` (or `== 0` for specificity tests).
