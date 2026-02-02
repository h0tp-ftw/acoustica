# 🚀 Deployment Guide: Acoustic Alarm Engine

This guide covers advanced deployment strategies, configuration details, and API integration for the Acoustic Alarm Engine.

---

## 🏗️ 1. Deployment Modes

The engine supports three primary modes of operation, depending on your hardware constraints and detection requirements.

### A. Standard Mode (Single Engine)

**Best for:** Simple devices detecting a single alarm type (e.g., just Smoke Alarms) or multiple alarms that share similar acoustic properties (similar speed/frequency).

- **Architecture**: One `Engine` instance processing audio.
- **Pros**: Lowest CPU/Memory footprint.
- **Cons**: All profiles must share the same sensitivity and timing settings.
- **Usage**:

  ```python
  from acoustic_engine import Engine, load_profiles_from_yaml

  profiles = load_profiles_from_yaml("all_profiles.yaml")
  engine = Engine(profiles=profiles)
  engine.start()
  ```

### B. Parallel Mode (Isolated Pipelines)

**Best for:** Detecting _dissimilar_ alarms simultaneously (e.g., a fast, quiet Medical Beep AND a slow, loud CO Alarm).

- **Architecture**: Multiple `Engine` instances running virtually in parallel, sharing a single Audio Listener string.
- **Pros**:
  - **Total Isolation**: Tuning the sensitivity for "CO Alarm" won't cause false positives for "Smoke Alarm".
  - **Optimized Resolution**: Fast alarms get 11ms chunks; slow alarms get 92ms chunks (efficiency).
- **Cons**: Slightly higher memory usage (~30MB per additional pipeline).
- **Usage**:

  ```python
  from acoustic_engine.parallel_engine import ParallelEngine
  from acoustic_engine.models import AlarmProfile

  # Load profiles
  smoke_profile = ...
  co_profile = ...

  # The ParallelEngine automatically creates optimized EngineConfig for each profile
  runner = ParallelEngine(pipelines=[smoke_profile, co_profile])
  runner.start()
  ```

### C. High-Resolution Mode

**Best for:** Detecting very fast beeps (<50ms) or rapid-fire patterns (e.g., modern microwave beeps, medical monitors).

- **Mechanism**: Forces the internal FFT and buffer size to be smaller (1024 samples vs 4096).
- **Trade-off**: Increases CPU usage slightly (more frequent processing) but achieves ~11ms temporal resolution.
- **Enable via Config**:
  ```yaml
  engine:
    chunk_size: 1024 # Force high-res
    min_tone_duration: 0.02
    dropout_tolerance: 0.04
  ```

---

## ⚙️ 2. Detailed Configuration Reference

The `GlobalConfig` is the single source of truth. It can be loaded from one or multiple YAML files.

### 📋 YAML Structure (`config.yaml`)

```yaml
# 1. System Settings
system:
  log_level: "INFO" # DEBUG, INFO, WARNING, ERROR
  log_file: "/var/log/acoustic_engine.log" # Optional

# 2. Audio Capture
audio:
  sample_rate: 44100 # Hz (Standard: 44100, 48000. Lower values like 16000 not recommended for high-freq alarms)
  chunk_size: 1024 # 1024 = High Res (~23ms), 4096 = Standard (~92ms)
  device_index: null # Integer index for specific microphone (see PyAudio)

# 3. Engine Tuning (The "DSP" Layer)
engine:
  min_magnitude:
    10.0 # Sensitivity Threshold. Lower = More sensitive.
    # Typical: 5.0 (Quiet rooms) to 20.0 (Noisy factories).

  min_sharpness:
    1.5 # Peak Prominence ratio. How much "pointier" a peak must be
    # compared to its neighbors. Higher = rejects white noise better.

  noise_floor_factor:
    3.0 # Dynamic Threshold. Signal must be X times stronger than the
    # median background noise.

  frequency_tolerance: 50.0 # Hz. How much a tone can drift and still count (e.g. 2950Hz - 3050Hz).

  # Temporal Resolution
  min_tone_duration: 0.05 # Seconds. Shortest valid beep.
  dropout_tolerance: 0.05 # Seconds. Max gap in valid signal allowed before "beep" is cut.

# 4. Alarm Profiles
profiles:
  - include: "profiles/smoke_alarm.yaml"
  - include: "profiles/co_detector.yaml"
  # Or define inline:
  - name: "Custom_Beep"
    confirmation_cycles: 2
    segments: [...]
```

### 🧠 Performance Tuning Guide

| Problem                                              | Adjustment                                                                                                                                                 |
| :--------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **False Negatives** (Alarm ringing but not detected) | 1. Decrease `min_magnitude` (e.g. 10.0 -> 5.0)<br>2. Increase `frequency_tolerance` (e.g. 50 -> 100)<br>3. Increase `dropout_tolerance` (e.g. 0.04 -> 0.1) |
| **False Positives** (Detecting alarm when silence)   | 1. Increase `min_sharpness` (1.5 -> 2.0)<br>2. Increase `confirmation_cycles` in profile (1 -> 2)<br>3. Tighten frequency range in profile.                |
| **High CPU Usage**                                   | 1. Increase `chunk_size` (1024 -> 4096)<br>2. Use `FrequencyFilter` (enabled by default) to ignore unused bands.                                           |
| **Misses Fast Beeps**                                | 1. Set `chunk_size: 1024` (High Res Mode)<br>2. Decrease `min_tone_duration` to 0.02.                                                                      |

---

## 📚 3. Python API Reference

### `Engine` Class

The core worker.

```python
class Engine:
    def __init__(
        self,
        profiles: List[AlarmProfile],
        audio_config: Optional[AudioSettings] = None,
        engine_config: Optional[EngineConfig] = None,
        on_detection: Optional[Callable[[str], None]] = None,
        on_match: Optional[Callable[[PatternMatchEvent], None]] = None
    ): ...
```

- `profiles`: List of patterns to look for.
- `engine_config`: If `None`, it is **auto-computed** based on the strictest requirements of the provided profiles.
- `on_detection`: Simple callback `func(name: str)`.
- `on_match`: Rich callback `func(event: PatternMatchEvent)`.

### `ParallelEngine` Class

The wrapper for multiple isolated pipelines.

```python
class ParallelEngine:
    def __init__(
        self,
        pipelines: List[Union[AlarmProfile, Tuple[AlarmProfile, EngineConfig]]],
        audio_config: Optional[AudioSettings] = None,
        ...
    ): ...
```

- `pipelines`: Can pass just a `list[AlarmProfile]`. The `ParallelEngine` will examine each profile and spin up a separate child `Engine` tailored specifically for that profile (e.g., one High-Res, one Standard).

### CLI Tools

#### `verify_profile.py`

Critical for pre-deployment checks.

```bash
python scripts/verify_profile.py \
  --audio recording.wav \
  --profile smoke_alarm.yaml \
  --high-res \       # Force high-resolution mode
  --dropout 0.1      # Override dropout tolerance
  --verbose          # Show every detected beep/pause event
```

---

## 🛡️ 4. Best Practices for Production

1.  **Hardware Selection**:

    - **Microphone**: MEMS microphones (I2S) are preferred over analog electret for digital consistency.
    - **Placement**: Don't bury the mic inside a plastic case without a port; consistent acoustic coupling is key.

2.  **Environment Calibration**:

    - Run the `scripts/measure_footprint.py` (if available) or simply log `max_magnitude` values in the target environment for 24 hours to determine the correct `min_magnitude` safety margin.

3.  **Watchdog Architecture**:

    - The `Engine.start()` method is blocking. Run it in a separate thread/process (use `start_async()`).
    - Monitor the process. If Python exits, restart it. The engine is stateless between restarts (except for the active alarm cooldown).

4.  **Profile Versioning**:
    - Store profiles in version control.
    - Always run regression tests (`pytest tests/`) after modifying any profile parameters.
