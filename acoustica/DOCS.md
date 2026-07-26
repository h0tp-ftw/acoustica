# Acoustica

Acoustica listens to a microphone connected to Home Assistant and exposes repetitive tonal patterns as binary sensors. Audio analysis is local.

## First setup

1. Start the Acoustica add-on.
2. Restart Home Assistant Core once so the bundled custom integration is loaded.
3. Open **Settings → Devices & services** and confirm the discovered **Acoustica** integration.
4. Open the add-on **Web UI** and confirm that Audio shows **listening**.

The default configuration enables smoke T3 and carbon-monoxide T4 detector presets.

## Web UI

The Web UI uses the Home Assistant host microphone. It does not request browser microphone access.

Use it to:

- inspect audio and Home Assistant health;
- choose a microphone;
- record, validate, and save an acoustic profile;
- enable a saved profile as a live detector;
- disable a live detector;
- inspect the most recent match or recovery error.

A microphone change is opened once as a preflight check before the add-on options are saved. When a new generation still fails during startup, Acoustica restores the previous working options and engine automatically.

## Storage

Saved profiles use add-on-owned persistent storage:

```text
/data/profiles
```

On upgrade, legacy YAML files from `/config/acoustica/profiles` are copied into that directory when a file of the same name is not already present.

## Home Assistant entities

Each configured detector becomes one binary sensor. Disabling a detector sends an immediate removal tombstone, so its existing entity becomes unavailable. Re-enabling the same profile revives that entity.

Home Assistant delivery is asynchronous. When Core is unavailable, the newest state for each detector remains queued and is retried. Heartbeat snapshots allow integration reloads to recover current state.

## Troubleshooting

### Audio is unavailable

Open the Web UI and select a microphone. Check the add-on log for PulseAudio sources, the default microphone mute state, and volume. Acoustica reports those values but does not change host-wide microphone gain.

### The integration does not appear

Start the add-on, restart Home Assistant Core once, then open **Settings → Devices & services**. Use **Add integration → Acoustica** only when Supervisor discovery does not appear.

### A profile cannot be deleted

Disable the live detector first. Active profile files are protected from deletion.

### A detector change failed

The runtime panel displays the latest recovery reason. A failed microphone preflight leaves the old generation running; an immediate candidate startup failure restores the prior saved options.

Acoustica supplements certified alarms and must not replace or silence them.
