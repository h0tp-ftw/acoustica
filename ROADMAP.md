# Alarm Audio Detector Roadmap

## Phase 1: Core Multi-Sensor Configuration

**Goal**: Enable easy configuration of multiple binary sensors for different alarm sounds

### Tasks
- Define configuration schema for multiple alarm sound profiles
- Each profile should include:
  - Unique sensor name/ID
  - Frequency range (low/high thresholds in Hz)
  - Amplitude threshold
  - Duration threshold (minimum sustained detection)
  - Optional: frequency weighting/adjustments
- Implement dynamic entity registration based on config
- Add `config_entries` flow for setup
- Create `manifest.json` with proper Home Assistant integration requirements
- Implement `binary_sensor` platform with entities created per profile

### Technical Notes
- Use `BinarySensorEntity` from `homeassistant.components.binary_sensor`
- Store config in `config_entries` with unique IDs
- Entities update via coordinator pattern (see `PassiveBluetoothProcessorCoordinator` as reference)

---

## Phase 2: Sensitivity Optimization & Testing

**Goal**: Optimize sensitivity for specific alarm sounds

### Tasks
- Add sensitivity tuning parameters:
  - Frequency bandpass filter (min/max Hz)
  - Amplitude gain multiplier
  - Noise floor threshold
  - Rise time detection window
  - Confidence scoring (0-100)
- Implement test mode:
  - Live audio visualization
  - Real-time metric display (frequency, amplitude, duration)
  - Detection threshold indicators
- Add config validation to warn about potentially conflicting settings
- Create documentation for common alarm sound profiles (smoke, CO, burglar, siren)

---

## Phase 3: Audio Analysis Tool

**Goal**: Tool to generate ideal configs from audio samples

### Options (choose one):
**A. Built-in Web Tool (Recommended)**
- Create HTTP endpoint in integration to serve web UI
- Upload audio file (MP3/WAV/OGG)
- Analyze frequency spectrum (FFT)
- Auto-detect peaks and patterns
- Generate suggested config with confidence scores
- Export as YAML

**B. Standalone Website**
- Separate web app with same analysis logic
- Import/export configs via YAML
- Potentially easier to maintain/share

### Core Features
- Audio waveform visualization
- Frequency spectrum analyzer
- Peak detection algorithms
- Pattern matching for repetitive alarm tones
- Suggested thresholds with explainers
- A/B comparison: test config against audio sample

---

## Phase 4: Predefined Config Library

**Goal**: Shareable, tested configurations for common alarm sounds

### Tasks
- Create `configs/` directory with YAML files:
  - `smoke_alarm_standard.yaml`
  - `co_detector_high_pitch.yaml`
  - `burglar_siren_multi_tone.yaml`
  - `fire_alarm_low_freq.yaml`
  - `doorbell_chime.yaml`
  - `medical_alert_pager.yaml`
- Document each profile:
  - Target device model/brand tested
  - Expected frequency range
  - Known false positives/negatives
- Add import/export functionality in UI
- Consider community contribution process

---

## Technical Architecture

### Core Components
```
alarm_audio_detector/
├── __init__.py          # Integration setup
├── manifest.json
├── config_flow.py       # Config entry setup UI
├── const.py             # Constants & defaults
├── binary_sensor.py     # Binary sensor entities
├── coordinator.py       # Audio processing coordinator
├── analyzer.py          # FFT & detection logic
├── api.py               # Web tool endpoints
├── configs/             # Predefined profiles
└── www/
    └── analysis.html    # Web analysis tool
```

### Audio Processing
- Capture via Home Assistant audio API (`/hardware/audio`)
- 16KHz, 16-bit mono PCM (standard for voice/audio)
- FFT analysis for frequency detection
- Rolling buffer for duration tracking

### Configuration Schema Example
```yaml
alarm_audio_detector:
  sensors:
    - name: "Smoke Alarm"
      unique_id: "smoke_alarm_kitchen"
      frequency_min: 2800
      frequency_max: 3200
      amplitude_threshold: 0.7
      duration_min_ms: 500
      confidence_threshold: 80
    - name: "CO Detector"
      unique_id: "co_detector_bedroom"
      frequency_min: 4000
      frequency_max: 4500
      amplitude_threshold: 0.6
      duration_min_ms: 300
      confidence_threshold: 70
```

---

## Future Enhancements (Post-MVP)
- Machine learning-based pattern recognition
- Multiple detection methods (frequency, pattern, ML)
- Recording detected audio snippets
- Integration with notification systems
- Historical detection logging
- Mobile app sensor display

---

## Dependencies & APIs to Research
- Home Assistant Audio Devices API (`/hardware/audio`)
- Wake Word Detection API pattern (for audio stream handling)
- Binary Sensor platform implementation
- Config Entries flow for multi-entity setup
- Versioned Home Assistant Core events for local push updates
