# Acoustica for Home Assistant

Acoustica listens to a microphone connected to Home Assistant and turns repetitive tonal sounds—smoke and CO alarms, appliance jingles, timers, and similar patterns—into Home Assistant binary sensors. Processing is local and powered by `acoustic-engine`.

> **Development release 10.4.0.** Acoustica supplements certified alarms; it does not replace them. Keep certified alarms installed, audible, tested, and maintained according to their instructions.

## Architecture

```text
Microphone
   │
   ▼
Acoustica add-on
  acoustic-engine capture, DSP, matching, tuner, profiles
  hot-reloadable detector generations
  bounded Home Assistant state publisher
   │ versioned Core events + Supervisor discovery
   ▼
Acoustica custom integration
  integration-owned binary sensors
  heartbeat availability and diagnostics
```

The detector callback never waits for Home Assistant. It queues only the newest state per profile, retries failed delivery, and periodically replays the latest snapshot so integration reloads recover automatically.

## Installation

1. Add this repository in **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Install and start **Acoustica**.
3. Restart Home Assistant Core once after the first start so the bundled custom integration is loaded.
4. Open **Settings → Devices & services** and confirm the discovered **Acoustica** integration.

The add-on currently copies its bundled integration to `/config/custom_components/acoustica` for compatibility with existing installs. Supervisor discovery handles the pairing flow after Home Assistant loads the integration. **Add integration → Acoustica** remains a manual fallback.

See [QUICKSTART.md](QUICKSTART.md) for the shortest setup path.

## Default detectors

The default add-on options enable the engine's standardized smoke T3 and carbon-monoxide T4 presets:

```yaml
detectors:
  - name: Smoke Alarm
    preset: smoke_t3
    device_class: smoke
  - name: CO Alarm
    preset: co_t4
    device_class: carbon_monoxide
sample_rate: 44100
device_index: -1
hold_seconds: 30
debug: false
```

`device_index: -1` means the system default microphone.

## Guided Web UI

Open the add-on **Web UI** through Home Assistant ingress. The existing acoustic-engine tuner remains the recording and validation surface. Acoustica injects a runtime panel that adds:

- listening, Home Assistant, active-match, and last-detection status;
- microphone enumeration and live selection;
- the list of active detectors;
- one-click enablement of saved canonical profiles;
- active-profile deletion protection.

The tuner records from the Home Assistant host microphone, not the browser microphone. Saved profiles are canonical engine YAML and are loaded directly by the production detector.

### Enable a learned profile

1. Record several repetitions of the sound in the tuner.
2. Review and validate the generated profile using the real engine pipeline.
3. Save it.
4. Choose a Home Assistant device class in the Acoustica runtime panel.
5. Select **Enable**.

Acoustica validates the complete candidate configuration, persists the complete option set through Supervisor, stops the current engine generation, and starts the new generation in the same process. Failed option persistence leaves the current runtime untouched.

### Profile storage and migration

New profiles are stored in add-on-owned persistent storage:

```text
/data/profiles/<profile>.yaml
```

On startup, profiles from older releases under `/config/acoustica/profiles` are copied into `/data/profiles` when a file with the same name does not already exist.

## Add-on options

Each detector entry must use one source:

| Source | Meaning |
| --- | --- |
| `preset` | Built-in `smoke_t3` or `co_t4`. |
| `profile` | Canonical YAML under `/data/profiles`; normally enabled through the Web UI. |
| `learn` | WAV under `/data/sounds`, learned on startup and saved as a profile. |

Supported Home Assistant device classes include `smoke`, `carbon_monoxide`, `gas`, `sound`, `moisture`, `safety`, `problem`, `running`, and `vibration`.

`hold_seconds` controls how long a sensor remains on after the last confirmed detection. Repeated matches rearm one clear timer.

## Home Assistant protocol

The add-on publishes the versioned event:

```text
acoustica_state
```

Example event data:

```json
{
  "protocol_version": 1,
  "profile_id": "Smoke Alarm",
  "device_class": "smoke",
  "active": true,
  "updated_at": "2026-07-26T12:00:00+00:00",
  "source_version": "10.4.0"
}
```

The integration rejects unrelated or unsupported payloads, creates entities dynamically from valid events, and marks a sensor unavailable after missed heartbeats.

## Runtime controls

The detector process exposes a loopback-only control API on `127.0.0.1:8100`. The ingress wrapper is the only intended client. It supports read-only health, profile activation, and microphone selection. The control service is not exposed as an add-on port.

## Development

From the `acoustica` directory:

```bash
python -m pytest
node --check tuner/acoustica-controls.js
```

Or run the complete local gate:

```bash
bash validate.sh
```

The validation script checks Python compilation, YAML/JSON parsing, JavaScript syntax when Node.js is available, the pytest suite, release-version consistency, and the container build when Docker is available.

Local tests cover configuration sources, real synthetic alarm matching, non-blocking state transport, retries and heartbeat snapshots, clear-timer rearming, Supervisor discovery, protocol validation, runtime reload rollback, microphone changes, ingress injection, profile deletion protection, and version consistency.

## Known release verification work

The source tree is locally validated, but the following still require an appliance-capable environment:

- multi-architecture container builds;
- microphone enumeration and index stability on Home Assistant OS;
- PulseAudio capture under the shipped AppArmor profile;
- Supervisor discovery and integration confirmation on a live Home Assistant instance;
- repeated hot reloads while real audio capture is active.

## Project layout

```text
acoustica/
├── config.yaml
├── Dockerfile
├── run.sh
├── detector/
│   ├── config.py
│   ├── integration_client.py
│   ├── ha_bridge.py
│   ├── control_server.py
│   ├── tuner_server.py
│   └── main.py
├── tuner/
│   ├── acoustica-controls.js
│   └── acoustica-controls.css
├── custom_components/acoustica/
├── tests/
└── validate.sh
```

## License

This project is licensed under the PolyForm Noncommercial License 1.0.0. The pinned `acoustic-engine` dependency has its own license and distribution terms.
