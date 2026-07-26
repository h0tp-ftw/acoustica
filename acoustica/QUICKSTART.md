# Acoustica Quick Start

Acoustica listens to a microphone attached to Home Assistant and turns repeating alarms, beeps, and short melodies into binary sensors.

## 1. Install the add-on

1. Open **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Add this repository and install **Acoustica**.
3. Start the add-on.

On first start, the add-on installs its bundled custom integration under Home Assistant's `custom_components/acoustica` directory.

## 2. Load and confirm the integration

Restart Home Assistant Core once after the first add-on start. Then open **Settings → Devices & services**.

Home Assistant should show a discovered **Acoustica** integration. Open it and confirm the setup. When discovery is unavailable, use **Add integration → Acoustica** as a manual fallback.

The default installation immediately listens for standard smoke and carbon-monoxide alarm patterns.

## 3. Open Easy Setup

Open the add-on **Web UI**. Easy Setup is the default page.

It shows:

- whether the microphone is listening;
- whether Home Assistant is connected;
- every detector currently active;
- every saved custom sound;
- any automatic recovery message after an audio problem.

Most users should leave the Home Assistant **Configuration** tab unchanged. Easy Setup handles the microphone, detector name, category, matching level, test, save, and activation.

## 4. Add your own sound

Select **Add a sound detector** and follow the five steps.

### Step 1 — Make sure Acoustica can hear

Choose a microphone and select **Test this microphone**. Make a short noise near it.

Acoustica reports one of these results:

- **Microphone sounds good** — continue;
- **Very quiet** — move the microphone closer;
- **Too loud** — move it farther away;
- **No clear sound heard** — check the device and mute state.

### Step 2 — Tell Home Assistant what the sound means

Choose a plain-language type such as:

- Smoke alarm;
- Carbon monoxide alarm;
- Appliance finished;
- Doorbell or chime;
- Water or leak alarm;
- Other warning sound;
- Something else.

Give it the name you want to see in Home Assistant, such as **Washing machine finished** or **Front door chime**.

### Step 3 — Teach Acoustica

Select **Start teaching recording**, then play the sound three to five times. Leave a little quiet space between repetitions and avoid talking during the recording.

After learning, choose:

- **Forgiving** when timing or volume changes;
- **Balanced** for most sounds;
- **Precise** when the sound is very consistent and avoiding false matches matters most.

You can switch between these choices freely. Each choice is rebuilt from the original learned pattern rather than from the previous setting.

### Step 4 — Test it with a fresh recording

Select **Start test recording** and play the sound again.

This recording is separate from the teaching sample. Acoustica only allows the normal save flow after the detector recognizes this fresh test.

When the test fails, the page explains whether the recording was quiet, clipped, missing clear tones, or simply did not match. You can make matching more forgiving, teach it again, or open Advanced tuning.

### Step 5 — Save and start listening

Review the name, Home Assistant type, matching level, and test result. Select **Save and start listening**.

The profile is saved to persistent add-on storage and activated without restarting the container.

## Tweak or retest later

The main Easy Setup page lists saved custom sounds and active detectors.

- Select **Tweak or retest** to change the matching level and make another fresh test.
- Select **Disable** to stop a detector. Its Home Assistant entity becomes unavailable immediately and can be revived later.
- Select **Advanced tuning** for waveforms, frequencies, timing ranges, YAML, and other expert controls.
- Select **Easy setup** in the Advanced view to return.

## Test certified alarms safely

Use the physical test control on the certified alarm and watch the matching binary sensor. Acoustica supplements certified alarms; it must not replace, disable, or reduce their normal audible operation.

## Common issues

| Symptom | Action |
| --- | --- |
| Acoustica integration is not listed | Start the add-on, restart Home Assistant Core once, then check Devices & services again. |
| No microphone is listed | Confirm a microphone is attached to the Home Assistant host and inspect the add-on log for PulseAudio sources. |
| The microphone test is quiet | Move the microphone closer or choose another input. Acoustica reports host gain but does not change it automatically. |
| The fresh test does not match | Try Forgiving matching, play more repetitions, reduce background noise, or teach the sound again. |
| Home Assistant is disconnected | Detection continues locally and the latest state remains queued for automatic retry. |
| A saved profile cannot be deleted | It is active. Select **Disable** beside the detector first. |
| A detector or microphone change fails | Read the automatic recovery message. The previous working generation should resume automatically. |
