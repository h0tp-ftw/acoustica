# Acoustica

Acoustica listens to a microphone connected to Home Assistant and exposes repetitive tonal patterns as binary sensors. Audio analysis is local.

## First setup

1. Start the Acoustica add-on.
2. Restart Home Assistant Core once so the bundled custom integration is loaded.
3. Open **Settings → Devices & services** and confirm the discovered **Acoustica** integration.
4. Open the add-on **Web UI**.

The default configuration enables smoke T3 and carbon-monoxide T4 detector presets. Most users should not edit the add-on **Configuration** tab; use Easy Setup instead.

## Easy Setup

Easy Setup is the default Web UI. It uses the Home Assistant host microphone and never requests access to the browser microphone.

The dashboard shows:

- plain-language microphone and Home Assistant health;
- active detectors;
- saved custom sounds;
- automatic recovery details;
- buttons to add, disable, tweak, or retest detectors.

### Add a detector

Select **Add a sound detector** and complete five steps:

1. Choose and test a microphone.
2. Choose what the sound means and name it.
3. Record three to five repetitions so Acoustica can learn the pattern.
4. Test the learned pattern against a separate recording.
5. Save and start listening.

The normal save path requires a successful fresh-recording test.

### Matching choices

Easy Setup replaces frequency and timing controls with three choices:

- **Forgiving** widens the learned ranges and needs fewer matching repetitions.
- **Balanced** keeps the learned ranges and is recommended for most sounds.
- **Precise** narrows the ranges and requires more matching repetitions.

Every choice is calculated from the original learned profile. Switching repeatedly does not accumulate changes.

### Tweak and retest

Saved custom sounds have a **Tweak or retest** action. Use it to change the matching choice and run another fresh test without teaching the sound from scratch.

### Advanced tuning

Select **Advanced tuning** for waveform inspection, raw frequency and timing ranges, YAML import/export, and other acoustic-engine controls. Select **Easy setup** to return.

## Runtime safety

A microphone change is opened once as a preflight check before the add-on options are saved. When a new generation still fails during startup, Acoustica restores the previous working options and engine automatically.

Saving a learned profile and enabling it is transactional. When activation fails, the previous profile file is restored or the new file is removed.

## Storage

Saved profiles use add-on-owned persistent storage:

```text
/data/profiles
```

On upgrade, legacy YAML files from `/config/acoustica/profiles` are copied into that directory when a file of the same name is not already present.

## Advanced Configuration tab

The Home Assistant add-on **Configuration** tab remains available for:

- built-in presets;
- manual profile references;
- startup learning from WAV files;
- sample-rate and hold-time changes;
- debug logging;
- scripted or migrated installations.

It is not required for normal detector setup.

## Home Assistant entities

Each configured detector becomes one binary sensor. Disabling a detector sends an immediate removal tombstone, so its existing entity becomes unavailable. Re-enabling the same profile revives that entity.

Home Assistant delivery is asynchronous. When Core is unavailable, the newest state for each detector remains queued and is retried. Heartbeat snapshots allow integration reloads to recover current state.

## Troubleshooting

### Audio is unavailable

Open Easy Setup and select a microphone. Run **Test this microphone**. Check the add-on log for PulseAudio sources, the default microphone mute state, and volume. Acoustica reports those values but does not change host-wide microphone gain.

### Teaching fails

Play a repetitive tonal sound three to five times, leave quiet gaps between repetitions, and reduce speech or other strong background noise. Non-tonal sounds such as voices or glass breaking are outside the engine's intended use.

### A fresh test fails

Follow the page guidance. Try Forgiving matching, move the microphone, play more repetitions, or make a new teaching recording.

### The integration does not appear

Start the add-on, restart Home Assistant Core once, then open **Settings → Devices & services**. Use **Add integration → Acoustica** only when Supervisor discovery does not appear.

### A profile cannot be deleted

Disable the live detector first. Active profile files are protected from deletion.

### A detector change failed

Easy Setup displays the latest recovery reason. A failed microphone preflight leaves the old generation running; an immediate candidate startup failure restores the prior saved options.

Acoustica supplements certified alarms and must not replace or silence them.
