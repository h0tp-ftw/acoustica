# 🔊 Acoustic Alarm Detector for Home Assistant

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm_Noncommercial_1.0.0-lightgrey.svg)](LICENSE)
&nbsp;**Non-commercial use only.**

Listen on a microphone (e.g. the HAOS machine's own mic) and turn alarms and
beeps — smoke/CO alarms, a washing-machine jingle, an oven timer — into Home
Assistant **binary sensors**. 100% local, no cloud, **no MQTT broker**.

Detection is powered by the standalone
[**acoustic-engine**](https://github.com/h0tp-ftw/acoustic-engine): deterministic
DSP (FFT + temporal pattern matching), not a neural network — low CPU, runs fine
on a Raspberry Pi, and needs no training data.

## How it works

```
            ┌─────────────────────── HAOS machine ───────────────────────┐
 microphone │  Add-on (this repo)                  Home Assistant Core    │
   ───────▶ │  acoustic-engine ──detection──▶ HA event ──▶ Integration    │
            │  (DSP + matching)               (event bus)   binary_sensor │
            └─────────────────────────────────────────────────────────────┘
```

There are **two parts**, both in this repo:

1. **The add-on** — captures audio and runs the engine. On each detection it fires
   an event on Home Assistant's event bus.
2. **The custom integration** — listens for those events and exposes one
   `binary_sensor` per detector, grouped under a single **Acoustic Alarm Detector**
   device (so it shows up under *Settings → Devices & Services* like any normal
   device). The add-on auto-installs it into `/config`.

## Installation

1. **Add this repository as a custom add-on repository**
   (*Settings → Add-ons → Add-on Store → ⋮ → Repositories*), paste this repo's
   URL, then install **Acoustic Alarm Detector**.
   *(Or copy this folder into `/addons/` for a local add-on.)*
2. **Start the add-on.** On first start it copies the companion integration into
   `/config/custom_components/` (watch the log for the confirmation).
3. **Restart Home Assistant Core once** (*Settings → System → Restart*) so the new
   integration is loaded.
4. **Add the integration:** *Settings → Devices & Services → + Add Integration →
   “Acoustic Alarm Detector” → Submit*. A device appears with one sensor per
   detector. You only do this once — it serves every detector.

With the default options you immediately get two sensors:
`binary_sensor.acoustic_alarm_detector_smoke_alarm` and
`binary_sensor.acoustic_alarm_detector_co_alarm`.

## Configuration

Each entry under `detectors` becomes one binary sensor. Give it **one** source:

| Source     | Meaning                                                                 |
| ---------- | ----------------------------------------------------------------------- |
| `preset`   | A built-in pattern: `smoke_t3` (smoke) or `co_t4` (carbon monoxide).    |
| `profile`  | A profile YAML you placed under `/config/acoustic_alarm_detector/profiles/`. |
| `learn`    | A recording (WAV) under `/config/acoustic_alarm_detector/sounds/` — the add-on turns it into a profile on first run. |

```yaml
detectors:
  - name: "Smoke Alarm"
    preset: "smoke_t3"
    device_class: "smoke"
  - name: "CO Alarm"
    preset: "co_t4"
    device_class: "carbon_monoxide"
  - name: "Washing Machine"
    profile: "washing_machine.yaml"   # see the examples in this repo's profiles/
    device_class: "running"
  - name: "Dryer"
    learn: "dryer.wav"                 # learned into profiles/dryer.yaml
    device_class: "sound"
sample_rate: 44100
# device_index: 1     # set only if you have several mics (see Troubleshooting)
hold_seconds: 30      # how long a sensor stays "on" after the last detection
debug: false
```

`device_class` controls the sensor's icon/semantics. Common values: `smoke`,
`carbon_monoxide`, `gas`, `sound`, `moisture`, `safety`, `problem`, `running`,
`vibration`. Unknown values fall back to `sound`.

## Make a detector from your own sound

Three options, easiest first:

1. **Learn from a recording (no DSP knowledge).** Record the sound (e.g. press
   your appliance's done-button), save it as a 16-bit mono WAV under
   `/config/acoustic_alarm_detector/sounds/`, and add a detector with
   `learn: "myfile.wav"`. The add-on extracts the tone/timing pattern and writes a
   profile to `…/profiles/myfile.yaml` you can inspect and tweak.
2. **Hand-write a profile YAML.** Copy one of the examples in [`profiles/`](profiles/)
   into `/config/acoustic_alarm_detector/profiles/`, edit the frequencies/durations,
   and reference it with `profile: "myfile.yaml"`. Bundles (multiple profiles in one
   file) are supported — each becomes its own sensor.
3. **Use the engine's browser tuner** for visual, validated tuning — see the
   [acoustic-engine docs](https://github.com/h0tp-ftw/acoustic-engine#profile-tuner-browser-app).

> The engine is built for **repetitive, tonal** sounds (alarms, beeps, jingles).
> It is *not* meant for one-off beeps or non-tonal sounds like speech, glass
> breaking, or a dog barking.

## Automations

The sensors are ordinary binary sensors — trigger on `to: "on"`:

```yaml
automation:
  - alias: "Smoke alarm alert"
    triggers:
      - trigger: state
        entity_id: binary_sensor.acoustic_alarm_detector_smoke_alarm
        to: "on"
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: "🚨 Smoke alarm detected!"
          message: "An acoustic smoke-alarm pattern was heard."
```

More examples (notifications, lights, TTS) in [`docs/AUTOMATIONS.md`](docs/AUTOMATIONS.md)
— update the `entity_id`s to the `binary_sensor.acoustic_alarm_detector_*` names.

## Troubleshooting

- **No sensors / integration missing:** start the add-on once, then **restart HA
  Core** before adding the integration (the integration files only load on a Core
  restart).
- **Nothing is detected / mic not working:** set `debug: true` and check the add-on
  log — it lists the PulseAudio sources and the audio backend it opened. Confirm
  *Settings → System → Hardware* shows your microphone. If you have more than one
  input, set `device_index` to the right one.
- **Misses a real alarm or false-triggers:** presets target standardized alarms
  (~3 kHz). For other sounds, prefer `learn`/a custom `profile` tuned to your sound.
  Raising/lowering tolerances lives in the profile YAML (see the engine's
  [profiles & tuning docs](https://github.com/h0tp-ftw/acoustic-engine/blob/main/docs/profiles.md)).
- **Sensor stays on too long / clears too fast:** adjust `hold_seconds`.

## Project layout

```
alarm-audio-detector/
├── config.yaml                 # Add-on manifest + options schema
├── Dockerfile, run.sh          # Add-on image + startup (audio + integration install)
├── requirements.txt            # Pins acoustic-engine
├── detector/                   # Thin bridge: options → engine → HA events
│   ├── config.py               #   read options.json → AlarmProfiles
│   ├── ha_bridge.py            #   detections → HA binary_sensor state
│   └── main.py                 #   wire ParallelEngine + bridge
├── custom_components/acoustic_alarm_detector/   # The HA integration (sensors)
├── profiles/                   # Example profile YAMLs you can copy & tweak
├── tests/test_addon.py         # End-to-end tests (no mic / no HA needed)
└── docs/                       # ALSA setup, automation examples
```

## Credits & license

Detection by [acoustic-engine](https://github.com/h0tp-ftw/acoustic-engine), by
**@h0tp-ftw**.

This add-on is licensed under the **PolyForm Noncommercial License 1.0.0** — see
[LICENSE](LICENSE). You may use, modify, and share it freely for **personal and any
other non-commercial** purpose, with credit to @h0tp-ftw. **Commercial use is not
permitted.** (PolyForm is purpose-built for software; Creative Commons advises
against using CC licenses for code.)
