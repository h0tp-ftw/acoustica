# Acoustica for Home Assistant

Acoustica listens to a microphone connected to Home Assistant and turns repetitive tonal sounds—smoke and CO alarms, appliance jingles, timers, and similar patterns—into Home Assistant binary sensors. Processing is local and powered by `acoustic-engine`.

> **Release 10.5.0.** Acoustica supplements certified alarms; it does not replace them. Keep certified alarms installed, audible, tested, and maintained according to their instructions.

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

`device_index: -1` means the system default microphone. Most users never need to edit these options; use **Web UI → Easy Setup** instead.

## Easy Setup Web UI

Open the add-on **Web UI** through Home Assistant ingress. Easy Setup is the default screen and keeps raw frequency, timing, waveform, and YAML controls out of the normal path.

The dashboard shows whether the microphone is listening, whether Home Assistant is connected, every active detector, saved custom sounds, and the latest automatic-recovery detail.

Select **Add a sound detector** and follow five steps:

1. **Make sure Acoustica can hear.** Choose a microphone and run a short level check with quiet, good, clipping, or no-audio guidance.
2. **What does this sound mean?** Choose a plain-language category and give it the name that should appear in Home Assistant.
3. **Teach Acoustica the sound.** Play the sound three to five times while Acoustica learns the production engine pattern.
4. **Test it with a fresh recording.** Play the sound again in a separate recording. Saving stays blocked until the detector recognizes it.
5. **Save and start listening.** The canonical profile is saved and activated in one action.

After learning, choose one matching level:

- **Forgiving** for sounds whose timing or volume changes;
- **Balanced** for most alarms and appliance chimes;
- **Precise** for highly consistent sounds where false matches are a concern.

Changing the matching level always starts from the original learned pattern, so users can switch freely while testing. A failed test offers a one-click move to Forgiving matching or a new teaching recording.

Saved custom sounds have a **Tweak or retest** action. Active detectors have a source-aware **Disable** action. Home Assistant receives an immediate removal tombstone when a detector is disabled and revives the existing entity when the same profile is enabled again.

The Web UI records from the Home Assistant host microphone, not the browser microphone. The complete acoustic-engine tuner remains one click away under **Advanced tuning**, with an **Easy setup** return button.

Acoustica validates the complete candidate configuration, stops the current generation, opens the candidate microphone as a preflight check, and only then persists the complete option set through Supervisor. A failed preflight or option write restarts the previous generation. If a newly committed generation still exits during its startup window, Acoustica restores the prior options and engine automatically.

### Profile storage and migration

New profiles are stored in add-on-owned persistent storage:

```text
/data/profiles/<profile>.yaml
```

On startup, profiles from older releases under `/config/acoustica/profiles` are copied into `/data/profiles` when a file with the same name does not already exist.

## Advanced add-on options

The Home Assistant **Configuration** tab is retained for upgrades, presets, scripting, and advanced/manual operation. Normal users should leave it unchanged and use Easy Setup.

Each manually configured detector entry must use one source:

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
  "detector_id": "acoustica",
  "profile_id": "Smoke Alarm",
  "device_class": "smoke",
  "active": true,
  "removed": false,
  "updated_at": "2026-07-26T12:00:00+00:00",
  "source_version": "10.5.0"
}
```

The integration rejects unrelated or unsupported payloads, creates entities dynamically from valid events, and marks a sensor unavailable after missed heartbeats.

## Runtime controls

The detector process exposes a loopback-only control API on `127.0.0.1:8100`. The ingress wrapper is the only intended client. It supports read-only health, profile activation, detector disable, and microphone selection. The control service is not exposed as an add-on port.

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

The validation script checks Python compilation, YAML/JSON parsing, JavaScript syntax when Node.js is available, the pytest suite, dependency locks, and release-version consistency. Dedicated GitHub Actions jobs run Home Assistant app linting, execute the full beginner wizard in headless Chrome, and build amd64 and aarch64 images.

Local tests cover configuration sources, real synthetic alarm matching, non-blocking state transport, retries and heartbeat snapshots, clear-timer rearming, Supervisor discovery, protocol validation, transactional runtime rollback, detector tombstones, microphone changes, beginner setup APIs, fresh-recording tests, atomic save rollback, UI contracts, profile deletion protection, startup supervision, dependency locking, and version consistency.

## Release verification

The maintainer has reported successful manual operation on a real Home Assistant OS installation. Exact host and microphone details were not captured in the repository, so future release sessions should record them using [docs/HAOS_VALIDATION.md](docs/HAOS_VALIDATION.md).

Acoustica supports amd64 and aarch64. Home Assistant deprecated armv7 and armhf app targets, so current releases do not advertise those unmaintained builds.

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
