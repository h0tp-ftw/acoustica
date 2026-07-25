# Acoustic Alarm Detector for Home Assistant

Local smoke, carbon-monoxide, and custom alarm-pattern detection using the microphone connected to Home Assistant.

> **Development status — 9.5.0:** the detector runtime, integration-owned state path, guided learning, microphone selection, live health, discovery, and hot profile activation are implemented and covered by automated tests. The container still needs appliance testing on Home Assistant OS, and the custom integration still requires manual development installation. This software supplements certified alarms; it does not replace them.

## What has been simplified

The production path now has exactly:

- one audio stream;
- one DSP and pattern engine (`acoustic-engine==1.4.0`);
- one canonical `AlarmProfile` YAML format;
- one startup command;
- one Home Assistant state protocol;
- one guided profile-learning workflow.

```text
Home Assistant microphone
        |
        +---------------------> guided recording buffer
        |                              |
        v                              v
acoustic-engine live detector    acoustic-engine learner
        |                              |
        |                        canonical YAML in /data/profiles
        v
non-blocking state publisher
        |
        | authenticated Home Assistant Core event
        v
custom integration runtime data
        |
        v
integration-owned binary sensor
```

The add-on never writes directly to `/api/states`, never installs integration files, and never writes to Home Assistant's configuration directory.

## Supported architectures

- `amd64`
- `aarch64`

The Dockerfile uses a pinned explicit Home Assistant base image. Docker is unavailable on the current development host, so image builds and real microphone startup still require verification on a Docker-capable Home Assistant development system.

## Development installation

### 1. Install the custom integration

Copy:

```text
custom_components/acoustic_alarm_detector
```

to:

```text
/config/custom_components/acoustic_alarm_detector
```

Restart Home Assistant.

### 2. Install and start the local add-on

Install this directory as a local Home Assistant app/add-on. For an initial smoke or CO preset, leave `profile_id` empty.

### 3. Confirm the discovered integration

After the add-on starts, Home Assistant should show a discovered **Acoustic Alarm Detector** integration. Open it and confirm the detector/profile details. Discovery uses the stable detector/profile identity, so restarting the add-on does not create duplicate entities.

When Supervisor discovery is unavailable, use **Settings → Devices & services → Add integration → Acoustic Alarm Detector** and enter the detector ID, profile ID, and alarm category manually.

The entity becomes available after its first valid add-on heartbeat. Older integration entries migrate to an explicit profile ID and the same stable detector/profile unique ID.

## Guided profile learning

Open the add-on's **Web UI** from Home Assistant.

1. Choose the microphone connected to the Home Assistant host. Applying a different device saves the selection and restarts the add-on once to reopen audio.
2. Enter a stable profile ID such as `hallway_smoke`.
3. Press **Record**.
4. Activate the alarm's physical test button and capture at least two full repetitions.
5. Press **Stop**, then **Analyze recording**.
6. Review the plain-language result and generated canonical YAML.
7. Save the profile. Samples marked **Review** require explicit approval; poor samples cannot be saved.
8. Run **Live test** from the saved-profile list. This listens with the saved profile but never publishes a Home Assistant alarm.
9. Choose the Home Assistant category and press **Activate**. The detector hot-swaps to the saved profile and persists the selection without restarting.
10. Confirm the newly discovered detector/profile entry when Home Assistant prompts. Existing Supervisor-discovered entries update and reload in place.

The UI records the add-on's existing production microphone stream. It does not use the browser, phone, or laptop microphone, and it contains no client-side frequency detector. Recordings are held only in memory, limited to 30 seconds, and temporary analysis files are removed immediately.

The live-health card shows whether audio is listening, whether Home Assistant delivery is connected or retrying, whether a profile is currently matched, and the most recent detection time. It provides corrective guidance without exposing the Supervisor token or raw internal state.

Saved profiles live in the add-on-owned persistent directory:

```text
/data/profiles/<profile_id>.yaml
```

The exact saved YAML is loaded by the production detector—there is no generated-to-runtime conversion layer.

## Add-on options

| Option | Purpose |
| --- | --- |
| `device_name` | Stable detector ID shared with the integration |
| `alarm_type` | Home Assistant category: `smoke`, `co`, or `safety` |
| `profile_id` | Saved profile to load; empty uses the built-in smoke/CO preset |
| `audio_device_index` | Selected host input index; `-1` uses the system default |
| `target_frequency` | Preset-only target tone frequency in Hz |
| `frequency_tolerance` | Preset-only allowed frequency range |
| `min_magnitude_threshold` | Preset-only minimum tone strength |
| `confirmation_cycles` | Preset-only repetitions required before activation |
| `reset_timeout` | Preset-only quiet time before clearing |
| `debug_mode` | Additional runtime diagnostics |

`alarm_type: safety` requires a saved `profile_id`. When `profile_id` is set, the canonical YAML owns timing, frequencies, confirmations, resolution, and clear timeout.

## Profile command-line backend

The ingress UI and command-line tool use the same `ProfileStore` service.

```bash
# Analyze without saving
python -m detector.profile_tool --profile-dir ./profiles-local \
  analyze alarm.wav --id hallway_alarm

# Analyze and save a strong sample
python -m detector.profile_tool --profile-dir ./profiles-local \
  learn alarm.wav --id hallway_alarm

# Import canonical engine YAML
python -m detector.profile_tool --profile-dir ./profiles-local \
  import profile.yaml --id hallway_alarm

# List or validate
python -m detector.profile_tool --profile-dir ./profiles-local list
python -m detector.profile_tool validate profiles/smoke_alarm_t3.yaml
```

A recording marked **Review** requires `--accept-review` before it can be saved.

## Home Assistant state protocol

The add-on posts one local event:

```text
acoustic_alarm_detector_state
```

Example payload:

```json
{
  "protocol_version": 1,
  "detector_id": "smoke_alarm_detector",
  "profile_id": "hallway_smoke",
  "active": true,
  "updated_at": "2026-07-25T12:00:00+00:00",
  "source_version": "9.5.0"
}
```

Delivery never blocks audio processing. The publisher retains only the newest value per profile, retries failures, and replays the latest snapshot every 60 seconds. The integration marks an entity unavailable after 150 seconds without a valid heartbeat.

## Development and validation

Install pinned dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run everything available locally:

```bash
bash validate.sh
```

The validation command checks Python compilation, YAML/JSON parsing, dependency integrity, JavaScript syntax when Node.js is available, architectural guardrails, and the pytest suite. It also builds the image when Docker is available.

Manual image build:

```bash
docker build --pull -t local/acoustic-alarm-detector:dev .
```

Current tests cover synthetic T3/T4 detection, profile learning and quality gates, canonical YAML round trips, add-on-owned storage, live-stream recording bounds, ingress HTTP operations, alarm clear deadlines, failure exits, state retries/heartbeats, integration protocol validation, stale availability, lifecycle cleanup, and version consistency.

## Repository layout

```text
Dockerfile                         Add-on image
config.yaml                        Home Assistant options and ingress
apparmor.txt                       Reduced permissions
run.sh                             Canonical startup
detector/
  main.py                          Audio/runtime orchestration
  config.py                        Preset or saved-profile loading
  detector.py                      Engine wrapper and clear deadline
  integration_client.py            Bounded non-blocking event publisher
  sensor.py                        Profile state routing
  profile_service.py               Learning, quality, validation, storage
  profile_server.py                Ingress API and live recording tap
  profile_tool.py                  CLI using the same profile service
custom_components/
  acoustic_alarm_detector/         Integration-owned entity and runtime state
tuner/
  index.html                       Guided setup UI
  app.js                           API controller only
  audio-engine.js                  Add-on recording API client
profiles/                          Example canonical profiles
tests/                             Pytest suite
```

## Remaining work

- Build and run the image on Home Assistant OS for both declared architectures.
- Verify PulseAudio capture, ingress source address, integration reload, and stale availability on an appliance.
- Replace manual custom-integration file installation with a supported distribution flow.
- Review the external engine's CC BY-NC 4.0 licensing before public distribution.

The detailed local roadmap is kept in the gitignored `DEVELOPMENT_PLAN.local.md` file.

## Safety

Detection can fail because of microphone placement, volume, background noise, hardware problems, configuration, or software defects. Keep certified smoke and CO alarms installed, tested, audible, and maintained according to their manufacturer instructions and local requirements.

## License

See [LICENSE](LICENSE). The external `acoustic-engine` dependency has separate license and distribution terms.
