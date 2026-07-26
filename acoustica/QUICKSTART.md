# Acoustica Quick Start

Acoustica listens to a microphone attached to Home Assistant and exposes detected alarm or appliance patterns as binary sensors.

## 1. Install the add-on

1. Open **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Add this repository and install **Acoustica**.
3. Start the add-on.

On first start, the add-on installs its bundled custom integration under `/config/custom_components/acoustica`.

## 2. Load and confirm the integration

Restart Home Assistant Core once after the first add-on start. Then open **Settings → Devices & services**.

Home Assistant should show a discovered **Acoustica** integration. Open it and confirm the setup. When discovery is unavailable, use **Add integration → Acoustica** as a manual fallback.

The default configuration creates smoke and carbon-monoxide detectors.

## 3. Check runtime health

Open the add-on **Web UI**. The Acoustica runtime panel shows:

- whether audio is listening;
- Home Assistant connection and queued updates;
- active acoustic matches and the most recent detection;
- the selected microphone;
- every detector currently running.

Select a different microphone in the panel when needed. Acoustica reopens the audio engine inside the running add-on; a container restart is not required.

## 4. Learn and enable another sound

Use the guided tuner in the Web UI:

1. Record the alarm or appliance using the Home Assistant host microphone.
2. Review the generated pattern and run the engine validation step.
3. Save the profile.
4. Choose its Home Assistant device class in the Acoustica panel.
5. Select **Enable**.

The complete add-on options are saved through Supervisor and the detector engine reloads in place. The corresponding Home Assistant entity receives an initial clear state automatically.

Saved profiles live in add-on-owned persistent storage at `/data/profiles`. Profiles from older installations under `/config/acoustica/profiles` are copied into the new location on startup.

## Test safely

Use the physical test control on the certified alarm and watch the matching binary sensor. Acoustica supplements certified alarms; it must not replace, disable, or reduce their normal audible operation.

## Common issues

| Symptom | Action |
| --- | --- |
| Acoustica integration is not listed | Start the add-on, restart Home Assistant Core once, then check Devices & services again. |
| Audio is unavailable | Open the Web UI, select a listed microphone, and inspect the add-on log for PulseAudio sources. |
| Home Assistant is disconnected | Detection continues locally and the latest state remains queued for automatic retry. |
| A saved profile cannot be deleted | It is active. Keep it, or remove that detector from the add-on configuration before deleting the file. |
| A new profile is not detecting | Run the tuner validation again with a clean recording containing multiple repetitions. |
