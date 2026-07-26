# Changelog

## 10.4.0

### Added

- Supervisor discovery for the Acoustica Home Assistant integration.
- Versioned, non-blocking Home Assistant state delivery with retry and heartbeat snapshots.
- Guided ingress runtime panel with health, microphone selection, profile activation, and detector disable controls.
- Add-on-owned profile storage under `/data/profiles` with migration from the legacy `/config/acoustica/profiles` directory.
- Immediate Home Assistant tombstones when a detector is disabled.
- Diagnostics and stale-availability handling in the custom integration.
- Locked runtime dependencies and GitHub Actions validation for amd64 and aarch64 images.

### Changed

- Audio and detector changes reload inside the running add-on instead of requiring a container restart.
- Microphone changes are preflighted before Supervisor options are committed.
- The previous working engine generation is automatically restored when a newly selected audio generation fails during startup.
- The tuner server is supervised and restarts after an unexpected exit.
- Startup reports microphone mute and volume state without changing host-wide gain settings.
- The add-on uses the current `homeassistant_config` mount and supports amd64/aarch64 only; deprecated armv7/armhf declarations were removed.

### Fixed

- Removed synchronous Home Assistant HTTP calls from the audio callback.
- Prevented deletion of profiles that are still active.
- Prevented simultaneous runtime reload requests from racing.
- Cleared and retired removed detectors explicitly instead of waiting for heartbeat expiry.

### Validation

- The maintainer reported successful manual operation on a real Home Assistant OS installation.
- The repository validation suite covers configuration, synthetic detection, transport retries, runtime rollback, detector lifecycle, ingress controls, dependency locking, and release metadata.
- CI builds amd64 and aarch64 Home Assistant images on every pull request and main-branch push.
