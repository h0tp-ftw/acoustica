# Integration Setup for Development Testing

The integration and add-on are separate components. The add-on never copies or overwrites Home Assistant integration files.

## 1. Install the custom integration

Copy:

```text
custom_components/acoustic_alarm_detector
```

to:

```text
/config/custom_components/acoustic_alarm_detector
```

Restart Home Assistant after copying or updating the integration.

## 2. Install and start the add-on

Install this project as a local add-on. For the initial run, use a built-in preset:

```yaml
device_name: smoke_alarm_detector
alarm_type: smoke
profile_id: ""
audio_device_index: -1
```

The add-on requires audio and `homeassistant_api: true`; both are already declared in `config.yaml`.

## 3. Optionally learn a custom profile

Open the add-on **Web UI**.

1. Choose the host microphone. Applying a different selection saves it and restarts the add-on once.
2. Enter a profile ID such as `hallway_smoke`.
3. Start recording the add-on's microphone.
4. Trigger the alarm test for at least two complete repetitions.
5. Stop, analyze, and review the result.
6. Save the profile.
7. Run **Live test** from the saved-profile list. The test never publishes a Home Assistant alarm.
8. Choose the Home Assistant category and press **Activate**. The add-on persists and hot-swaps the profile without restarting.

The generated YAML is stored in `/data/profiles` and is loaded directly by the production detector.

## 4. Confirm the discovered integration entry

After the add-on starts, Home Assistant should surface a discovered **Acoustic Alarm Detector** integration. Open it and confirm the detector ID, active profile ID, and alarm category.

The add-on republishes discovery after profile changes. Both discovered and manual setup use the stable detector/profile pair as the config-entry identity, so an add-on restart cannot create a duplicate entry.

When discovery is unavailable, open **Settings → Devices & services → Add integration → Acoustic Alarm Detector** and enter the same values manually.

The binary sensor initially appears unavailable. It becomes available when the add-on sends the first valid heartbeat. The alarm category controls only the binary-sensor device class.

## 5. Verify communication

In the add-on log, look for the Home Assistant publisher connection and queued clear state.

In Home Assistant:

1. Open **Developer tools → States**.
2. Find the Acoustic Alarm Detector binary sensor.
3. Confirm it is available.
4. Use a controlled alarm test to verify activation and clearing.

The entity attributes include detector ID, profile ID, alarm category, last update/heartbeat times, and add-on source version.

## Troubleshooting

### Entity remains unavailable

- Confirm the add-on is running.
- Confirm both components use the same detector ID and profile ID.
- Check the add-on log for a missing `SUPERVISOR_TOKEN` or Core API failure.
- Confirm `homeassistant_api: true` remains in `config.yaml`.
- Reload the integration; the add-on replays its latest state every 60 seconds.

### Saved profile does not start

- Confirm the YAML exists under `/data/profiles/<profile_id>.yaml`.
- Confirm the saved profile appears in the Web UI.
- Try **Live test** before activation and check the add-on logs for validation errors.
- Activate the profile from the Web UI; the active profile cannot be deleted until another one is selected.

### Duplicate or unmanaged entity

The current code does not write to `/api/states`, and discovered/manual flows share a stable unique ID. Remove entities left over from older test versions and reload the integration.

### Integration does not appear

- Confirm the directory is named `acoustic_alarm_detector`.
- Confirm `manifest.json` is directly inside that directory.
- Restart Home Assistant and check the Core log for custom-component errors.

### Add-on cannot access audio

Open the add-on Web UI and refresh the microphone list. Select the host input and apply it; the add-on restarts once to reopen the stream. The add-on does not change microphone gain automatically, and the guided recorder uses the same stream as live detection.

## Current limitation

Manual custom-integration file installation remains development-only. Guided calibration, hot activation, and Supervisor discovery are implemented; a supported integration distribution path remains future work.
