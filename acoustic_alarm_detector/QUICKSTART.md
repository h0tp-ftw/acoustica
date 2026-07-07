# 🚀 Quick Start

Get a smoke + CO alarm sensor running in a few minutes. Full details in
[README.md](README.md).

## 1. Install & start the add-on

- *Settings → Add-ons → Add-on Store → ⋮ → Repositories* → add this repo's URL.
- Install **Acoustic Alarm Detector**, then **Start** it.
- The add-on copies its companion integration into `/config/custom_components/`
  (check the log).

## 2. Load the integration

- **Restart Home Assistant Core once** (*Settings → System → Restart*).
- *Settings → Devices & Services → + Add Integration → “Acoustic Alarm Detector”
  → Submit*.

You now have an **Acoustic Alarm Detector** device with:

- `binary_sensor.acoustic_alarm_detector_smoke_alarm`
- `binary_sensor.acoustic_alarm_detector_co_alarm`

## 3. Test it

- Press the **Test** button on a real smoke/CO alarm near the mic, **or**
- Set `debug: true` in the add-on options and watch the log — it prints the mic it
  opened and every tone it hears.

The sensor flips to **Detected** (on) when the pattern is heard and clears after
`hold_seconds` (default 30s).

## 4. Add your own sounds

In the add-on **Configuration** tab, add a detector:

```yaml
detectors:
  - name: "Washing Machine"
    learn: "washer.wav"        # put the WAV in /config/acoustic_alarm_detector/sounds/
    device_class: "running"
```

or point `profile:` at a YAML you placed in
`/config/acoustic_alarm_detector/profiles/` (copy an example from
[`profiles/`](profiles/)). Restart the add-on after changing detectors; reload the
integration (or restart Core) to pick up brand-new sensors.

## Common issues

| Symptom | Fix |
| --- | --- |
| Integration not in the list | Restart **HA Core** after first starting the add-on. |
| No detections | `debug: true`, check the log for the mic; set `device_index` if you have several. |
| New detector has no sensor | Reload the integration (or restart Core) after adding it. |
