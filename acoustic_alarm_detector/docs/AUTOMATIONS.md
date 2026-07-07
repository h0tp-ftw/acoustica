# =============================================================================
# HOME ASSISTANT AUTOMATION EXAMPLES FOR ACOUSTIC ALARM DETECTOR
# =============================================================================

# -----------------------------------------------------------------------------
# 1. MOBILE NOTIFICATION WITH HIGH PRIORITY (iOS/Android)
# -----------------------------------------------------------------------------
automation:
  - alias: "Smoke Alarm - Critical Mobile Alert"
    description: "Send high-priority notification when smoke alarm detected"
    triggers:
      - trigger: state
        entity_id: binary_sensor.smoke_alarm_detector
        to: "on"
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: "🚨 SMOKE ALARM DETECTED"
          message: "Acoustic smoke alarm pattern detected at {{ now().strftime('%I:%M %p') }}"
          data:
            # Android-specific settings
            channel: "Smoke_Alarm"
            importance: high
            ledColor: "red"
            vibrationPattern: "100,1000,100,1000,100,1000"
            persistent: true
            sticky: true
            ttl: 0
            priority: high

            # iOS-specific settings
            push:
              sound:
                name: "default"
                critical: 1
                volume: 1.0

            # Actions for quick response
            actions:
              - action: "SILENCE_ALARM"
                title: "Silence"
              - action: "CALL_911"
                title: "Call 911"
              - action: "VIEW_CAMERAS"
                title: "View Cameras"

# -----------------------------------------------------------------------------
# 2. ALEXA ANNOUNCEMENT TO ALL ECHO DEVICES
# -----------------------------------------------------------------------------
  - alias: "Smoke Alarm - Alexa Announcement"
    description: "Announce smoke alarm on all Alexa devices"
    triggers:
      - trigger: state
        entity_id: binary_sensor.smoke_alarm_detector
        to: "on"
    actions:
      - action: notify.alexa_media
        data:
          message: >
            <amazon:emotion name="excited" intensity="high">
              Attention! Smoke alarm has been detected in the home!
              Please evacuate immediately and check for fire!
            </amazon:emotion>
          data:
            type: announce
          target:
            - media_player.bedroom_echo
            - media_player.kitchen_echo
            - media_player.living_room_echo

# -----------------------------------------------------------------------------
# 3. TELEGRAM NOTIFICATION WITH CAMERA SNAPSHOT
# -----------------------------------------------------------------------------
  - alias: "Smoke Alarm - Telegram with Camera"
    description: "Send Telegram message with camera snapshots"
    triggers:
      - trigger: state
        entity_id: binary_sensor.smoke_alarm_detector
        to: "on"
    actions:
      - action: notify.telegram
        data:
          title: "🚨 SMOKE ALARM DETECTED"
          message: "Smoke alarm detected at {{ now().strftime('%I:%M %p on %B %d, %Y') }}"

      # Send camera snapshots
      - action: telegram_bot.send_photo
        data:
          url: "{{ states.camera.living_room.attributes.entity_picture }}"
          caption: "Living Room Camera - Smoke Alarm Event"

      - action: telegram_bot.send_photo
        data:
          url: "{{ states.camera.kitchen.attributes.entity_picture }}"
          caption: "Kitchen Camera - Smoke Alarm Event"

# -----------------------------------------------------------------------------
# 4. SMART HOME EMERGENCY RESPONSE
# -----------------------------------------------------------------------------
  - alias: "Smoke Alarm - Emergency Protocol"
    description: "Automated emergency response when alarm detected"
    triggers:
      - trigger: state
        entity_id: binary_sensor.smoke_alarm_detector
        to: "on"
    actions:
      # Turn on ALL lights to 100%
      - action: light.turn_on
        target:
          entity_id: all
        data:
          brightness_pct: 100
          color_name: "red"

      # Unlock all doors for evacuation
      - action: lock.unlock
        target:
          entity_id:
            - lock.front_door
            - lock.back_door

      # Open garage door
      - action: cover.open_cover
        target:
          entity_id: cover.garage_door

      # Turn off HVAC to prevent smoke circulation
      - action: climate.turn_off
        target:
          entity_id: climate.thermostat

      # Flash lights for visual alert (5 times)
      - repeat:
          count: 5
          sequence:
            - action: light.turn_off
              target:
                entity_id: all
            - delay: "00:00:01"
            - action: light.turn_on
              target:
                entity_id: all
              data:
                brightness_pct: 100

# -----------------------------------------------------------------------------
# 5. LOG ALARM EVENTS TO DATABASE
# -----------------------------------------------------------------------------
  - alias: "Smoke Alarm - Event Logging"
    description: "Log all alarm events for historical analysis"
    triggers:
      - trigger: state
        entity_id: binary_sensor.smoke_alarm_detector
        to: "on"
    actions:
      - action: logbook.log
        data:
          name: "Smoke Alarm Detector"
          message: "Smoke alarm detected via acoustic monitoring"
          entity_id: binary_sensor.smoke_alarm_detector

      # Store event in input_datetime for tracking
      - action: input_datetime.set_datetime
        target:
          entity_id: input_datetime.last_smoke_alarm
        data:
          datetime: "{{ now().isoformat() }}"

# -----------------------------------------------------------------------------
# 6. NIGHT MODE - ENHANCED ALERTS
# -----------------------------------------------------------------------------
  - alias: "Smoke Alarm - Night Mode Enhanced"
    description: "Extra loud alerts if alarm triggers at night"
    triggers:
      - trigger: state
        entity_id: binary_sensor.smoke_alarm_detector
        to: "on"
    conditions:
      - condition: time
        after: "22:00:00"
        before: "06:00:00"
    actions:
      # Play siren sound on all speakers
      - action: media_player.play_media
        target:
          entity_id:
            - media_player.bedroom_speaker
            - media_player.living_room_speaker
        data:
          media_content_id: "/local/sounds/alarm_siren.mp3"
          media_content_type: "music"

      # Set volume to maximum
      - action: media_player.volume_set
        target:
          entity_id: all
        data:
          volume_level: 1.0

      # Vibrate smart watch
      - action: notify.mobile_app_watch
        data:
          message: "SMOKE ALARM!"
          data:
            presentation_options:
              - alert
              - badge
            push:
              interruption-level: critical

# -----------------------------------------------------------------------------
# 7. FALSE ALARM RESET
# -----------------------------------------------------------------------------
  - alias: "Smoke Alarm - Auto Clear After Investigation"
    description: "Automatically clear alarm state after 5 minutes"
    triggers:
      - trigger: state
        entity_id: binary_sensor.smoke_alarm_detector
        to: "on"
        for: "00:05:00"
    actions:
      - action: notify.mobile_app_your_phone
        data:
          message: "Smoke alarm state auto-cleared after 5 minutes"