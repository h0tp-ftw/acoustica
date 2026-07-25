# Acoustic Alarm Detector Integration

Home Assistant custom integration for entities owned by the Acoustic Alarm Detector add-on.

## Development installation

1. Copy this directory to:

   ```text
   /config/custom_components/acoustic_alarm_detector/
   ```

2. Restart Home Assistant.
3. Start the add-on.
4. Open the discovered **Acoustic Alarm Detector** card under **Settings → Devices & services** and confirm it.

Use **Add integration → Acoustic Alarm Detector** only as a manual fallback. Both setup paths use the stable detector/profile unique ID, so republished Supervisor discovery cannot create duplicates.

Supported integration distribution is still being developed. The add-on does not copy or modify these files automatically.

## State ownership

The integration exclusively owns the Home Assistant binary sensor. The add-on publishes a versioned local event through the authenticated Home Assistant Core API. The integration validates the protocol version plus detector/profile IDs, stores the latest state in config-entry runtime data, and updates the entity through Home Assistant's normal entity lifecycle.

There is no direct `/api/states` write and no custom WebSocket command.

## Entity behavior

- The selected smoke category uses the smoke binary-sensor device class.
- The selected CO category uses the dedicated CO device class.
- Learned profiles can use the generic safety category without changing their profile ID.
- The entity remains unavailable until the first matching state event arrives.
- Profile ID, alarm category, latest add-on update time, and source version are exposed as attributes.
- Entries created before profile IDs existed migrate to their previous smoke/CO profile and a stable detector/profile unique ID automatically.
- Event and dispatcher subscriptions are removed with the config entry.

## Version

9.5.0
