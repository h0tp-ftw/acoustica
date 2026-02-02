# 🔊 Acoustic Engine

## The Open Standard for IoT Sound Recognition

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC_BY--NC_4.0-lightgrey.svg?style=for-the-badge)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Embedded Ready](https://img.shields.io/badge/Embedded-Ready-success?style=for-the-badge&logo=arm&logoColor=white)](#)

A high-performance, noise-resilient DSP library designed to detect specific acoustic patterns (Smoke Alarms, CO Detectors, Appliance Beeps) on lightweight hardware.

> [!TIP]
> **Why this engine?** Unlike heavy Neural Networks, the Acoustic Engine uses deterministic Digital Signal Processing (DSP) to achieve high accuracy with low CPU usage. Best for battery-powered or resource-constrained IoT devices.

## ✨ Features

- **Noise Resilient**: Event analysis that ignores background interference (-15dB SNR).
- **Efficient**: Real-time FFT with <5% CPU usage on Raspberry Pi.
- **Easy Config**: Simple YAML profiles for alarm definitions.
- **Grandmaster Robustness**: Advanced Reverb/Echo rejection and Frequency Drift tracking.

---

## 🚀 Quick Start

### 📦 Fastest Method (Pip)

The easiest way to get started is to install the package directly from PyPI.

```bash
pip install acoustic-engine
```

**Running the Engine:**

```bash
# Run with a configuration file
python -m acoustic_engine.runner --help
```

---

### 🐳 Docker Method (Linux Only)

**Note:** Linux only due to OS restrictions. Windows/Mac users should use the **Pip Method** above.
For an isolated environment without installing system dependencies:

```bash
docker run -it --rm --device /dev/snd -v $(pwd):/app python:3.11-slim-bookworm \
  sh -c "apt-get update -qq && apt-get install -y portaudio19-dev gcc > /dev/null && pip install acoustic-engine && python -m acoustic_engine.runner --help"
```

---

## 🎯 Use Cases

- **💨 Life Safety**: Industry-standard Smoke (T3) and CO (T4) alarm detection.
- **🍳 Appliances**: Detect microwave beeps, oven timers, or dishwasher completion chimes.
- **🏥 Medical**: Monitor critical patient equipment alarms in noisy hospitals.
- **🏭 Industrial**: Identify specific machinery fault codes or safety buzzers in high-reverb warehouses.
- **🏠 Smart Home**: Trigger automation when your doorbell or dryer buzzes.

---

## 🏆 Robustness & Benchmarks

The Acoustic Alarm Engine is engineered for "Grandmaster" grade durability.

The Acoustic Alarm Engine is engineered for "Grandmaster" grade durability in real-world environments where simple detectors fail.

### **Elite Performance Metrics (for correctly defined configurations)**

- **Extreme Noise Resilience**: Confirmed detection at **-15dB SNR** (White/Pink Noise) and robust performance against **Chaotic Spectral Noise**.
- **Spectral Subtraction**: New **Per-Bin Noise Profiling** allows the engine to "learn" and subtract stationary noise (fans, HVAC, motors), effectively making it invisible to the detector.
- **Dynamic Background Rejection**: Tested against "Cocktail Party" scenarios (speech babble + clattering dishes). The engine correctly identifies alarms even when the background noise level exceeds the alarm volume (**Negative SNR**).
- **Echo/Reverb Rejection**: Internal **Dip-Disconnect** logic allows the engine to "hear through" reverb decays of up to **50%**. Excellent for warehouses, tiled hallways, and large industrial spaces.
- **Frequency Drift Tracking**: Automatically follows "dying piezo" buzzers that sweep through frequencies (tested up to **200Hz drift**) without losing lock.
- **Alarm Collision Isolation**: Successfully isolates and detects a target T3 alarm even while a louder T4 distractor alarm is sounding in a different frequency lane.
- **Absolute Specificity**: Zero False Positives when tested against "imposter" timers with similar but incorrect rhythms (e.g., 0.3s beeps vs 0.5s targets).

### **Best Suited For:**

- 💨 **Smoke & CO Alarms**: Perfect for industry-standard T3 and T4 patterns.
- 🏠 **Smart Homes**: Survives loud TVs, music, and dinner parties.
- 👨‍🍳 **Busy Kitchens**: Ignores blenders, banging pots, and microwave beeps.
- 🏥 **Medical Equipment**: Resilient to the chaotic acoustic environments of hospitals.
- 🏭 **Industrial Warehouses**: Built-in echo rejection for high-reverb spaces.
- 🍳 **Appliance Monitoring**: Differentiates between ovens, microwaves, and dishwashers.

### **NOT Suited For:**

- ❌ **Single / Lone Beeps**: A single beep is too generic and will lead to false positives. The engine relies on _repetition_ (rhythm) for specificity.
- ❌ **Complex Non-Tonal Sounds**: Dog barks, glass breaking, or speech. (Use a Neural Network for these).
- ❌ **Inconsistent Repetitions**: Sounds that change rhythms every time (e.g., a complex musical doorbell).
- ❌ **Variable Melodies**: Tunes that change notes every time (e.g., a complex musical doorbell).

---

### 💻 Development Setup (From Source)

For contributors or those who want to modify the engine code:

```bash
git clone https://github.com/h0tp-ftw/acoustic-engine.git
cd acoustic-engine
pip install -e .
```

### Basic Usage

```python
from acoustic_engine import Engine, AudioConfig
from acoustic_engine.profiles import load_profiles_from_yaml

# Load alarm profiles
profiles = load_profiles_from_yaml("profiles/smoke_alarm.yaml")

# Create engine with callback
engine = Engine(
    profiles=profiles,
    audio_config=AudioConfig(sample_rate=44100, chunk_size=4096),
    on_detection=lambda name: print(f"🚨 ALARM: {name}")
)

# Start listening (blocking)
engine.start()
```

## 🧠 Comparison: DSP vs Neural Networks

Why not use AI? While Neural Networks (NN) are powerful for general sounds (dogs barking, glass breaking), this DSP-based engine excels in **precision** and **efficiency**.

| Metric          | Acoustic Engine (DSP) | Neural Network (Edge AI) |
| :-------------- | :-------------------- | :----------------------- |
| **CPU**         | **3-5%** (Pi 4)       | 25-80%                   |
| **Latency**     | **~50ms**             | 200ms+                   |
| **Determinism** | **100%** (Math)       | Probabilistic            |
| **Data Needed** | **None** (Zero-shot)  | Thousands of samples     |

## Note that data IS needed for generation of the configuration file, but not for runtime.

## 🛠 How to Create a Custom Configuration

Using the default configuration is suitable for testing, but for production, you **must** create a custom configuration tailored to your specific hardware and target sound.

### 1. Identify and Record

Use the [Web Tuner](https://github.com/h0tp-ftw/acoustic-engine) to record your target alarm in its real environment. Ensure you capture the sound with the actual microphone hardware you intend to use.

### 2. Generate Configuration File

The [Web Tuner](https://github.com/h0tp-ftw/acoustic-engine) allows you to visually analyze the audio and generate a robust YAML profile. This ensures your profile accounts for the specific frequency response and noise characteristics of your setup. You might have to tweak the profile a bit to get it just right. For comprehensive tuning recipes (like Smart Home vs. Warehouse settings), see the [Tuning Guide](docs/tuning_guide.md). For more info on the configuration file format, see [Profile Schema](#profile-schema).

### 3. Test the Configuration

# Live testing (uses default microphone)

python -m acoustic_engine.runner --config configs/my_custom_alarm.yaml

# Testing against a WAV file

python scripts/verify_profile.py --audio my_recording.wav --profile profiles/my_profile.yaml

## 📋 Alarm Profiles policy

### **Recommended Workflow**

To ensure reliable detection, do not rely on guessed timings or stock examples.

1.  **One Sound = One Profile**: Create a dedicated YAML file for _each_ distinct alarm sound you want to detect.
2.  **Record Real Audio**: Use the **Web Tuner** (`python -m acoustic_engine.tuner`) to record the _actual_ device you are targeting in its real environment.
3.  **Verify**: Run the verification script against your recording before deploying:
    ```bash
    python scripts/verify_profile.py --audio my_recording.wav --profile my_profile.yaml
    ```

### Profile Schema

Define patterns in YAML. **Note that this section is just a reference.** In production, you will embed these profiles directly into your main configuration file (see below).

```yaml
name: "SmokeAlarm_T3"
confirmation_cycles: 2 # Require 2 complete cycles before triggering

segments:
  # Beep 1
  - type: "tone"
    frequency: { min: 2900, max: 3200 }
    duration: { min: 0.4, max: 0.6 }

  # Short pause
  - type: "silence"
    duration: { min: 0.1, max: 0.3 }

  # Beep 2
  - type: "tone"
    frequency: { min: 2900, max: 3200 }
    duration: { min: 0.4, max: 0.6 }

  # Inter-cycle pause
  - type: "silence"
    duration: { min: 0.8, max: 1.5 }
```

---

## ⚡ Technical Specifications

Designed for deployment on everything from powerful servers to low-power embedded gateways.

### Resource Consumption

_Measured on Standard/High-Performance Linux Workstation (x86_64)_

| Resource         | Idle   | Active (Listening) | Active (Detection) |
| :--------------- | :----- | :----------------- | :----------------- |
| **RAM**          | ~37 MB | ~40 MB             | ~43 MB             |
| **CPU (1 Core)** | < 1%   | < 1%               | < 1%               |

### Requirements

- **Python 3.9+**
- **System Dependencies**:
  - `portaudio` (Required for PyAudio microphone access)
- **Python Libraries** (installed automatically):
  - `numpy`
  - `scipy`
  - `PyAudio`
  - `PyYAML`

### **Detection Philosophy**

| Capability           | **Acoustic Alarm Engine**        | **Neural Networks (CNN/RNN)** |
| -------------------- | -------------------------------- | ----------------------------- |
| **Determinism**      | 100% (Mathematical)              | Probabilistic (Statistical)   |
| **Data Required**    | None (Zero-shot configuration)   | Thousands of labeled samples  |
| **Explainability**   | Clear (Matches frequency/rhythm) | "Black Box" (Weights-based)   |
| **Noise Resilience** | Elite in high-frequency rumble   | Great at complex soundscapes  |
| **Failing Hardware** | Trackable (via 200Hz drift)      | Often viewed as "Unknown"     |

**The Verdict**: Use this engine for **specific, repetitive patterns** (alarms, beeps, machinery) where performance and reliability are critical. Use Neural Networks for **general semantic sounds** (shouting, glass breaking, dog barking) where the patterns are too irregular for mathematical modeling.

---

## ⚙️ Configuration & Parallel Execution

The engine uses a **"One File per Runner"** philosophy. Instead of a complex, centralized "god config", you create a single, self-contained YAML file for each specific surveillance task (e.g., `smoke_alarm.yaml`, `co_sensor.yaml`).

> [!TIP]
> For advanced deployment strategies (Standard vs. Parallel vs. High-Res modes) and production best practices, see the [Deployment Guide](DEPLOYMENT.md).

### 1. The Configuration File

Each file completely defines the audio settings, engine sensitivity, and the alarm profile itself.

```yaml
# configs/smoke_alarm.yaml
system:
  log_level: "INFO"

audio:
  sample_rate: 44100
  chunk_size: 1024

engine:
  min_magnitude: 10.0 # High sensitivity for smoke alarms
  min_sharpness: 1.5

profiles:
  - name: "Smoke_T3"
    confirmation_cycles: 2
    segments:
      # Pattern: Beep (0.5s) - Silence (0.5s) - Beep (0.5s) - Silence (0.5s) - Beep (0.5s) - Long Silence (1.5s)

      # Beep 1
      - type: "tone"
        frequency: { min: 2800, max: 3200 }
        duration: { min: 0.45, max: 0.55 }
      - type: "silence"
        duration: { min: 0.45, max: 0.55 }

      # Beep 2
      - type: "tone"
        frequency: { min: 2800, max: 3200 }
        duration: { min: 0.45, max: 0.55 }
      - type: "silence"
        duration: { min: 0.45, max: 0.55 }

      # Beep 3
      - type: "tone"
        frequency: { min: 2800, max: 3200 }
        duration: { min: 0.45, max: 0.55 }

      # Inter-cycle pause (1.5s)
      - type: "silence"
        duration: { min: 1.2, max: 1.8 }
```

### 2. Running in Parallel

You can run multiple independent detection tasks on the same device by providing multiple config files. The engine acts as a **Parallel Runner**, executing each configuration in complete isolation (besides sharing the microphone).

```bash
python -m acoustic_engine.runner \
  --config configs/smoke_alarm.yaml \
  --config configs/co_sensor.yaml
```

- **Smart Negotiation**: The system automatically scans all configs and selects the highest audio quality settings (e.g., 44.1kHz) to ensure all runners operate at peak fidelity.
- **Total Isolation**: Adjusting the sensitivity in `smoke_alarm.yaml` has zero effect on the detection logic of `co_sensor.yaml`.

---

---

## 📋 Alarm Profiles

Define patterns in YAML:

```yaml
name: "SmokeAlarm_T3"
confirmation_cycles: 2 # Require 2 complete cycles before triggering

segments:
  # Beep 1
  - type: "tone"
    frequency: { min: 2900, max: 3200 }
    duration: { min: 0.4, max: 0.6 }

  # Short pause
  - type: "silence"
    duration: { min: 0.1, max: 0.3 }

  # Beep 2
  - type: "tone"
    frequency: { min: 2900, max: 3200 }
    duration: { min: 0.4, max: 0.6 }

  # Inter-cycle pause
  - type: "silence"
    duration: { min: 0.8, max: 1.5 }
```

### Optional Windowing Parameters

```yaml
window_duration: 10.0 # Seconds to analyze (auto-calculated if omitted)
eval_frequency: 0.5 # How often to evaluate windows
```

---

## 🧪 Testing Profiles

### With Audio Files

```bash
python -m acoustic_engine.tester \
  --profile profiles/smoke_alarm.yaml \
  --audio examples/audio/smoke_alarm.mp3 \
  -v
```

### Live Microphone

```bash
python -m acoustic_engine.tester \
  --profile profiles/ \
  --live \
  --duration 60
```

### With Noise Mixing (Specificity Testing)

```bash
python -m acoustic_engine.tester \
  --profile profiles/smoke_alarm.yaml \
  --audio examples/audio/smoke_alarm.mp3 \
  --noise 0.3 \
  --noise-type white
```

Noise types: `white`, `pink`, `brown`

---

## 🎛 Web Tuner

Visually record, analyze, and design alarm profiles:

```bash
python -m acoustic_engine.tuner
# Open http://localhost:8080
```

---

## 🏗 Architecture

The Acoustic Alarm Engine is built as a highly modular 4-stage processing pipeline, designed for deterministic performance and extreme reliability in difficult acoustic environments.

```mermaid
graph TD
    subgraph "Input Layer"
        MIC[🎤 Microphone] --> AL[AudioListener]
        FILE[📄 Audio File] --> PR[Manual Processing]
        SYN[⚡ Synthetic Data] --> PR
    end

    subgraph "Processing Layer (DSP)"
        AL --> SM[SpectralMonitor<br/>FFT + Peak Detection]
        PR --> SM
        SM --> FF[FrequencyFilter<br/>Noise Screener]
    end

    subgraph "Analysis Layer"
        FF --> EG[EventGenerator<br/>Peaks ➔ Tones]
        EG --> WM[WindowedMatcher<br/>Sliding Window Pattern Matching]
    end

    subgraph "Output Layer"
        WM --> CB[🚀 Callbacks / Detections]
    end

    subgraph "Configuration"
        YP[📄 YAML Profiles] --> WM
        CONFIG[⚙️ GlobalConfig] --> AL
        CONFIG --> SM
    end

    style MIC fill:#f9f,stroke:#333,stroke-width:2px
    style CB fill:#8f8,stroke:#333,stroke-width:2px
    style YP fill:#f96,stroke:#333,stroke-width:2px
```

### **1. Input Layer ([Detailed Docs](src/acoustic_engine/input/README.md))**

The engine is hardware-agnostic. While it includes a `PyAudio` implementation for live capture, it can process audio from any source (files, network streams, etc.) via the `process_chunk` interface.

### **2. Processing Layer ([Detailed Docs](src/acoustic_engine/processing/README.md))**

- **SpectralMonitor**: Performs Real-Time FFT and identifies peaks. It uses an **adaptive noise floor** to remain robust as ambient sound levels change.
- **FrequencyFilter**: Acts as a "firewall" that discards all audio frequencies not explicitly defined in your loaded profiles, preventing non-alarm sounds from wasting CPU cycles.

### **3. Analysis Layer ([Detailed Docs](src/acoustic_engine/analysis/README.md))**

- **EventGenerator**: Debounces spectral peaks, bridging transient dropouts and ensuring only "stable" tones are processed.
- **WindowedMatcher**: Uses a sliding window algorithm instead of a fragile state machine. This allows it to "see" a pattern even if it's surrounded by impulsive noise or if the recording started mid-beep.

See [ARCHITECTURE.md](ARCHITECTURE.md) for a deep dive into the implementation details.

---

## ⚙️ Configuration

The engine is highly configurable via a single YAML file or programmatically via `GlobalConfig`.

### **Universal Config Structure**

```yaml
system:
  log_level: "INFO" # DEBUG, INFO, WARNING, ERROR

audio:
  sample_rate: 44100 # Hz
  chunk_size: 1024 # FFT window size
  device_index: null # Specific mic index (null for default)

engine:
  min_magnitude: 10.0 # Sensitivity (lower = more sensitive)

  # Advanced Tuning
  min_sharpness: 1.5 # Rejects wide-band noise
  noise_floor_factor: 3.0 # Adaptive threshold multiplier
  frequency_tolerance: 50.0 # Hz drift tolerance
  dip_threshold: 0.6 # Instant dip disconnect (reverb rejection)

profiles:
  - include: "profiles/smoke_alarm.yaml"
```

### **Advanced Parameter Reference**

| Category  | Parameter            | Default | Description                                                       |
| :-------- | :------------------- | :------ | :---------------------------------------------------------------- |
| **DSP**   | `min_sharpness`      | `1.5`   | Ratio a peak must be above its neighbors to be considered a tone. |
| **DSP**   | `noise_floor_factor` | `3.0`   | Multiplier for the median-based adaptive noise floor.             |
| **Gen**   | `dip_threshold`      | `0.6`   | Detects a sudden magnitude drop to "disconnect" reverb tails.     |
| **Gen**   | `freq_smoothing`     | `0.3`   | Alpha for EMA frequency tracking (higher = faster tracking).      |
| **Match** | `noise_skip_limit`   | `2`     | Number of non-matching events to ignore before breaking a cycle.  |
| **Match** | `duration_relax_low` | `0.8`   | Multiplier for the minimum duration of a segment.                 |

---

## 📖 API Reference

### Engine

```python
Engine(
    profiles: List[AlarmProfile],
    audio_config: Optional[AudioConfig] = None,
    on_detection: Optional[Callable[[str], None]] = None,
    on_match: Optional[Callable[[PatternMatchEvent], None]] = None,
)
```

### AudioConfig

```python
AudioConfig(
    sample_rate: int = 44100,
    chunk_size: int = 4096,
    channels: int = 1,
    device_index: Optional[int] = None
)
```

### AlarmProfile

```python
AlarmProfile(
    name: str,
    segments: List[Segment],
    confirmation_cycles: int = 1,
    reset_timeout: float = 10.0,
    window_duration: Optional[float] = None,  # Auto-calculated if None
    eval_frequency: float = 0.5,
)
```

---

## 🛠 Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run integration test
python test_windowed.py
```

---

## 📄 License

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**.

- **Attribution**: You must give appropriate credit to me, @h0tp-ftw on github.com.
- **Non-Commercial**: You may not use the material for commercial purposes.

See [LICENSE](LICENSE) for the full text.
