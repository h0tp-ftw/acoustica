"""Bridge engine detections to Home Assistant binary_sensor entities.

The engine calls :meth:`HABridge.on_detection` with a profile name each time a
pattern is confirmed. We turn that into Home Assistant state by firing an event
on HA's event bus (via the Supervisor REST proxy); the companion custom
integration listens for the event and flips the matching binary_sensor.

Two things the engine deliberately leaves to us:

- **Turning OFF.** ``on_detection`` only ever fires on *detection*, never on
  clear. So each detection sets the sensor ON and (re)arms a per-detector timer
  that sets it OFF ``hold_seconds`` after the last detection — the sensor stays
  on while the alarm keeps sounding, then clears once it stops.
- **Existing before the first alarm.** We push every sensor OFF at startup so the
  entities appear immediately, and write a discovery file the integration reads.
"""

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# Event the add-on fires and the custom integration listens for.
EVENT_TYPE = "acoustic_alarm_detector_event"


class HABridge:
    """Maps engine detections onto Home Assistant binary_sensor states."""

    def __init__(
        self,
        device_classes: Dict[str, str],
        hold_seconds: float = 30.0,
        base_url: str = None,
        token: str = None,
        profiles_path=None,
    ):
        """
        Args:
            device_classes: profile name -> binary_sensor device_class.
            hold_seconds: how long a sensor stays ON after the last detection.
            base_url: HA API base. Defaults to the Supervisor proxy; override
                via ``HA_BASE_URL`` (used for local testing against a mock).
            token: bearer token. Defaults to ``SUPERVISOR_TOKEN``.
            profiles_path: where to write the discovery JSON. Override via
                ``PROFILES_JSON``.
        """
        self.device_classes = dict(device_classes)
        self.hold_seconds = hold_seconds
        self.base_url = (
            base_url or os.getenv("HA_BASE_URL") or "http://supervisor/core/api"
        ).rstrip("/")
        self.token = token if token is not None else os.getenv("SUPERVISOR_TOKEN", "")
        self.profiles_path = Path(
            profiles_path
            or os.getenv("PROFILES_JSON", "/config/acoustic_alarm_detector/profiles.json")
        )

        self._lock = threading.Lock()
        self._timers: Dict[str, threading.Timer] = {}
        self._states: Dict[str, bool] = {}

    # -- lifecycle ---------------------------------------------------------- #

    def setup(self) -> None:
        """Write the discovery file and push every sensor to a known OFF state."""
        self._write_profiles()
        if not self.token and "supervisor" in self.base_url:
            logger.warning(
                "No SUPERVISOR_TOKEN found — cannot push state to Home Assistant. "
                "Check that 'homeassistant_api: true' is set for the add-on."
            )
        for name in self.device_classes:
            self._states[name] = False
            self._send(name, False)

    def shutdown(self) -> None:
        """Cancel timers and clear every sensor (so a stopped add-on reads OFF)."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        for name in self.device_classes:
            self._send(name, False)

    # -- detection callback ------------------------------------------------- #

    def on_detection(self, name: str) -> None:
        """Engine callback: a pattern named ``name`` was just confirmed."""
        if name not in self.device_classes:
            # An unconfigured profile somehow fired; default its class so the
            # integration can still create a sensor for it.
            logger.warning("Detection for unknown detector '%s'; defaulting class.", name)
            self.device_classes[name] = "sound"

        self._set(name, True)

        with self._lock:
            old = self._timers.pop(name, None)
            if old:
                old.cancel()
            timer = threading.Timer(self.hold_seconds, self._clear, args=(name,))
            timer.daemon = True
            self._timers[name] = timer
            timer.start()

    def _clear(self, name: str) -> None:
        self._set(name, False)
        with self._lock:
            self._timers.pop(name, None)

    # -- state + transport -------------------------------------------------- #

    def _set(self, name: str, state: bool) -> None:
        """Send a state change, skipping redundant repeats of the same value."""
        with self._lock:
            if self._states.get(name) == state:
                return
            self._states[name] = state
        self._send(name, state)

    def _send(self, name: str, state: bool) -> None:
        device_class = self.device_classes.get(name, "sound")
        logger.info("%s -> %s", name, "DETECTED" if state else "clear")
        self._fire_event({"name": name, "state": bool(state), "device_class": device_class})

    def _fire_event(self, payload: dict) -> None:
        # On HAOS without a token there's nothing we can do; skip quietly (already
        # warned at setup). For local tests base_url is not the proxy, so we post.
        if not self.token and "supervisor" in self.base_url:
            return

        url = f"{self.base_url}/events/{EVENT_TYPE}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            logger.error("HA event POST failed: %s %s", e.code, e.reason)
        except Exception as e:  # URLError, timeouts, etc. — never kill detection
            logger.error("HA event POST failed: %s", e)

    # -- discovery ---------------------------------------------------------- #

    def _write_profiles(self) -> None:
        """Write the list of (name, device_class) the integration creates sensors from."""
        try:
            self.profiles_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "profiles": [
                    {"name": name, "device_class": dc}
                    for name, dc in self.device_classes.items()
                ]
            }
            self.profiles_path.write_text(json.dumps(payload, indent=2))
            logger.info("Wrote discovery file %s", self.profiles_path)
        except OSError as e:
            logger.error("Failed to write discovery file %s: %s", self.profiles_path, e)
