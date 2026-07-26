# Acoustica Home Assistant Integration

This companion integration exposes one Home Assistant `binary_sensor` for each detector reported by the Acoustica add-on. All sensors are grouped under one Acoustica device.

The add-on currently installs this directory under `/config/custom_components/acoustica` for compatibility. Restart Home Assistant Core once after the first add-on start. Supervisor discovery should then offer an **Acoustica** integration confirmation; **Add integration → Acoustica** is the manual fallback.

## Protocol

The add-on publishes versioned `acoustica_state` events through the authenticated Home Assistant Core API proxy. Event payloads include:

- `protocol_version`;
- `profile_id`;
- `device_class`;
- `active`;
- `updated_at`;
- `source_version`.

The integration validates the protocol, creates entities dynamically from valid events, and ignores unrelated or unsupported payloads. It marks a detector unavailable after its heartbeat expires and exposes non-sensitive diagnostics through Home Assistant.

No MQTT broker, shared discovery file, direct entity-state write, or custom WebSocket command is used.

## Files

```text
__init__.py        Config-entry lifecycle, event listener, stale timers
binary_sensor.py   Integration-owned binary sensor entities
config_flow.py     Supervisor discovery confirmation and manual fallback
const.py           Protocol parsing and constants
runtime.py         Per-profile runtime state
diagnostics.py     Config-entry diagnostics
manifest.json
strings.json
translations/en.json
```

Version 10.4.0
