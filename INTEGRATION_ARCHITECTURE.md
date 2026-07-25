# Home Assistant Integration Architecture

## Design rule

The add-on detects sounds. The custom integration owns Home Assistant entities. They communicate through exactly one versioned Home Assistant event.

```text
Microphone
   |
   v
Add-on
  AudioListener -> acoustic-engine -> PatternDetector
       |                              |
       v                              v
  bounded recording tap     IntegrationClient worker
       |
       v
  acoustic-engine learner -> canonical /data profile YAML
                                      |
                    POST /api/events/acoustic_alarm_detector_state
                                      |
                                      v
Home Assistant event bus -> custom integration -> managed binary sensor
```

## Add-on responsibilities

- Capture one mono microphone stream.
- Feed the same chunks to live detection and the bounded guided-recording tap.
- Run the published `acoustic-engine` detector and learner.
- Store validated canonical profiles only in add-on-owned `/data` storage.
- Maintain active/clear timing.
- Publish the latest profile state without blocking audio processing.
- Retain one pending value per profile during an outage.
- Periodically replay the latest snapshot so integration reloads recover.

The add-on does not write entity states directly and does not access Home Assistant configuration files.

## Integration responsibilities

- Create and own devices and binary-sensor entities.
- Register one event listener per config entry.
- Filter events by stable detector and profile IDs.
- Reject malformed or unsupported protocol versions.
- Update entities through Home Assistant's dispatcher/entity lifecycle.
- Remove subscriptions when the config entry unloads.

The integration does not capture audio or perform DSP.

## Protocol

Event type:

```text
acoustic_alarm_detector_state
```

Payload version 1:

```json
{
  "protocol_version": 1,
  "detector_id": "smoke_alarm_detector",
  "profile_id": "smoke",
  "active": true,
  "updated_at": "2026-07-25T12:30:00+00:00",
  "source_version": "9.3.0"
}
```

`detector_id` and `profile_id` must match the integration config entry. The integration ignores all unrelated events. `profile_id` identifies the engine pattern; the integration's separate `alarm_type` field controls the Home Assistant device class.

## Availability and recovery

The entity starts unavailable. The add-on publishes an initial clear state and periodically replays its latest state. The first matching valid event marks the entity available.

During a Home Assistant outage, the publisher queue remains bounded to one latest value per profile. A newer state replaces an older unsent state. Delivery retries in the background and does not block the audio loop.

## Security boundary

The add-on uses:

- `homeassistant_api: true`;
- the Supervisor-provided bearer token;
- the internal `http://supervisor/core/api` proxy;
- network access and the Home Assistant audio socket.

It does not require:

- `hassio_api: true`;
- `/config` or `/homeassistant` mappings;
- broad Home Assistant file access;
- a custom WebSocket endpoint;
- MQTT.

## Supervisor discovery

The add-on declares one `acoustic_alarm_detector` discovery service and publishes the active detector ID, profile ID, alarm category, protocol version, and source version through `POST /discovery`. Home Assistant invokes the integration's reserved `hassio` config-flow step and asks the user to confirm the discovered entry.

Both discovered and manual setup use the stable `detector_id + profile_id` unique ID. The Supervisor discovery UUID is transport metadata only and is never used as entity identity. This prevents duplicate entries when the add-on restarts or republishes discovery.

The `/discovery*` Supervisor endpoints are available to apps without broad `hassio_api` access, so discovery does not expand the permission boundary.
