# 🎛️ Acoustic Alarm Engine Tuning Guide

This guide explains how to tune the `EngineConfig` and `AlarmProfile` parameters to optimize detection for your specific environment.

## ⚙️ Engine Configuration (`EngineConfig`)

These global settings control how the engine processes audio _before_ looking for specific patterns. They control sensitivity, noise rejection, and spectral resolution.

### **Sensitivity & Detection Thresholds**

| Parameter       | Default | Description                                                    | Tuning Advice                                                                                                                                                |
| :-------------- | :------ | :------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `min_magnitude` | `10.0`  | The absolute minimum energy a peak must have to be considered. | **Lower (e.g., 5.0)** for very quiet alarms.<br>**Higher (e.g., 20.0)** if you are getting false positives from background hiss.                             |
| `min_sharpness` | `1.5`   | How much "pointier" a peak must be compared to its neighbors.  | **Higher (e.g., 2.0)** for pure tones like digital beeps.<br>**Lower (e.g., 1.2)** for "buzzing" or electromechanical alarms that aren't perfect sine waves. |
| `max_peaks`     | `5`     | Maximum number of peaks to track per 23ms chunk.               | **Increase (e.g., 8)** if you have multiple simultaneous alarms.<br>**Decrease (e.g., 3)** to save CPU on low-end devices.                                   |

### **Noise Rejection (Spectral Subtraction)**

| Parameter             | Default | Description                                          | Tuning Advice                                                                                                                                                                                                                    |
| :-------------------- | :------ | :--------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `noise_floor_factor`  | `3.0`   | How far above the background noise a signal must be. | **Increase (e.g., 5.0)** in erratic environments (machinery).<br>**Decrease (e.g., 2.0)** in quiet rooms to detect deeper signals.                                                                                               |
| `noise_learning_rate` | `0.01`  | How fast the engine "learns" steady noise.           | **Higher (e.g., 0.05)** adapts faster to fans turning on/off but might learn the alarm itself if it's too long.<br>**Lower (e.g., 0.005)** provides ultra-stable background estimation but reacts slowly to environment changes. |

### **Reverb & Echo Handling**

| Parameter       | Default | Description                                    | Tuning Advice                                                                                                                                                                                |
| :-------------- | :------ | :--------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dip_threshold` | `0.6`   | Detects the "cliff edge" at the end of a beep. | **Increase (e.g., 0.8)** for very dry signals.<br>**Decrease (e.g., 0.4)** for high-reverb warehouses where the beep tails off slowly. This helps the engine "cut" the tail and see the gap. |

---

## 📋 Profile Configuration (`AlarmProfile`)

These settings define the _shape_ of the sound you are looking for.

### **Basic Segments**

An alarm is defined as a sequence of `tone` and `silence` matching specific criteria.

```yaml
segments:
  - type: tone
    frequency: { min: 2900, max: 3100 } # Hz
    duration: { min: 0.4, max: 0.6 } # Seconds
  - type: silence
    duration: { min: 0.4, max: 0.6 }
```

### **High-Resolution Mode**

For very fast beeps (e.g., "Fast T4" or data transmission chirps), standard settings might merge the beeps. Use the `resolution` block in your profile:

```yaml
resolution:
  min_tone_duration: 0.03 # Default 0.1s. Set lower for fast chirps.
  dropout_tolerance: 0.03 # Default 0.15s. Lower this so gaps aren't "bridged".
```

- **`min_tone_duration`**: The shortest blip of sound the engine will register as a "Tentative Event".
- **`dropout_tolerance`**: How long a tone can disappear (due to noise/interference) before the engine decides "The beep has ended."

### **Confirmation & Reset**

| Parameter             | Default | Description                                                                                                                                    |
| :-------------------- | :------ | :--------------------------------------------------------------------------------------------------------------------------------------------- |
| `confirmation_cycles` | `1`     | How many full pattern repetitions are needed to trigger `on_detection`. Set to `2` or `3` for critical safety systems to prevent false alarms. |
| `reset_timeout`       | `10.0`  | If the pattern stops for this long, the match progress is reset to 0.                                                                          |

---

## 🧪 Tuning Recipes

### **Scenario 1: The "Smart Home" (TV, Music, Talking)**

- **Goal**: Ignore speech and movies, detect smoke alarm.
- **Config**:
  - `min_magnitude`: 15.0 (Ignore quiet background babble)
  - `noise_floor_factor`: 4.0 (Require strong signal)
  - `noise_learning_rate`: 0.05 (Adapt quickly to scene changes)

### **Scenario 2: The "Warehouse" (Forklifts, Echo, Fans)**

- **Goal**: Hear through reverb and stationary fan drone.
- **Config**:
  - `dip_threshold`: 0.4 (Aggressive tail cutting for echo)
  - `noise_learning_rate`: 0.005 (Slow learning to build a stable profile of the constant ventilation hum)
  - `min_sharpness`: 1.2 (Allow slightly "fuzzy" tones due to distance)

### **Scenario 3: "Dying Battery" Detector**

- **Goal**: Detect chirps that drift in frequency.
- **Config**:
  - `frequency_tolerance`: 100.0 (Allow ±100Hz drift)
  - `min_tone_duration`: 0.05 (Battery chirps are short)
