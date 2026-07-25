"""Thin add-on wrapper around the published acoustic-engine pipeline."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol

import numpy as np
from acoustic_engine import Engine
from acoustic_engine.config import AudioSettings
from acoustic_engine.events import PatternMatchEvent
from acoustic_engine.models import AlarmProfile

logger = logging.getLogger(__name__)


class _Timer(Protocol):
    daemon: bool

    def start(self) -> None: ...

    def cancel(self) -> None: ...


TimerFactory = Callable[[float, Callable[[], None]], _Timer]
DetectionCallback = Callable[[bool], None]


class _MatchForwardingEngine(Engine):
    """Use acoustic-engine's pipeline while forwarding every confirmed match."""

    def __init__(
        self,
        profile: AlarmProfile,
        audio_config: AudioSettings,
        on_match: Callable[[PatternMatchEvent], None],
    ) -> None:
        self._match_handler = on_match
        super().__init__(profiles=[profile], audio_config=audio_config)

    def _trigger_alarm(self, match: PatternMatchEvent) -> None:
        """Forward every match; add-on state management owns the clear deadline."""

        self._match_handler(match)


class PatternDetector:
    """Process audio and expose stable active/clear state callbacks."""

    def __init__(
        self,
        profile: AlarmProfile,
        audio_config: AudioSettings,
        on_detection: DetectionCallback | None = None,
        *,
        timer_factory: TimerFactory = threading.Timer,
    ) -> None:
        self.profile = profile
        self.name = profile.name
        self.on_detection = on_detection
        self.alarm_active = False

        self._timer_factory = timer_factory
        self._clear_timer: _Timer | None = None
        self._generation = 0
        self._lock = threading.Lock()
        self._engine = _MatchForwardingEngine(
            profile=profile,
            audio_config=audio_config,
            on_match=self._handle_match,
        )

        logger.info("Acoustic engine ready for profile %s", profile.name)

    def process(self, audio_chunk: np.ndarray) -> bool:
        """Process one mono int16 audio chunk."""

        return self._engine.process_chunk(audio_chunk)

    def _handle_match(self, match: PatternMatchEvent) -> None:
        """Activate once and extend the clear deadline on every later match."""

        should_notify_active = False
        with self._lock:
            self._generation += 1
            generation = self._generation

            if self._clear_timer is not None:
                self._clear_timer.cancel()

            if not self.alarm_active:
                self.alarm_active = True
                should_notify_active = True

            timer = self._timer_factory(
                self.profile.reset_timeout,
                lambda: self._clear_if_current(generation),
            )
            timer.daemon = True
            self._clear_timer = timer

        if should_notify_active:
            self._notify(True)
        timer.start()

        logger.warning(
            "Alarm match: %s (cycle %s); clear deadline extended by %.1fs",
            match.profile_name,
            match.cycle_count,
            self.profile.reset_timeout,
        )

    def _clear_if_current(self, generation: int) -> None:
        should_notify_clear = False
        with self._lock:
            if generation != self._generation or not self.alarm_active:
                return

            self.alarm_active = False
            self._clear_timer = None
            should_notify_clear = True

        if should_notify_clear:
            logger.info("Profile %s is clear", self.profile.name)
            self._notify(False)

    def close(self) -> None:
        """Cancel pending work and publish a final clear state once."""

        should_notify_clear = False
        with self._lock:
            self._generation += 1
            if self._clear_timer is not None:
                self._clear_timer.cancel()
                self._clear_timer = None
            if self.alarm_active:
                self.alarm_active = False
                should_notify_clear = True

        if should_notify_clear:
            self._notify(False)

    def _notify(self, detected: bool) -> None:
        if self.on_detection is None:
            return
        try:
            self.on_detection(detected)
        except Exception:
            logger.exception("Detection callback failed for profile %s", self.profile.name)
