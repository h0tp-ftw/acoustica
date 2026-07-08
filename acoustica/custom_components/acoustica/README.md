# Acoustica — Home Assistant integration

The companion integration for the **Acoustica add-on**. It exposes
one `binary_sensor` per detector the add-on reports, all grouped under a single
**Acoustica** device.

You normally don't install this by hand — the add-on copies it into
`/config/custom_components/` on first start. After that:

1. Restart Home Assistant Core once.
2. *Settings → Devices & Services → + Add Integration → “Acoustica”*.

## How it works

- The add-on does the listening and fires an `acoustica_event` on
  Home Assistant's event bus (`{name, state, device_class}`) via the Supervisor
  REST proxy — no MQTT broker, no websocket auth.
- This integration listens for that event and updates the matching sensor. Sensors
  are created from the add-on's discovery file
  (`/config/acoustica/profiles.json`) at setup, and any detector not
  yet seen is added automatically the first time its event arrives.
- One config entry serves every detector (single instance).

## Files

```
__init__.py        # config entry + event-bus listener
binary_sensor.py   # the sensor entities (one device, N sensors)
config_flow.py     # single confirm step
const.py           # DOMAIN, event/discovery paths
manifest.json
strings.json, translations/en.json
```

Version 10.0.0
