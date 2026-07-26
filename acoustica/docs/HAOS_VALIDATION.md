# Home Assistant OS validation

## Current evidence

The maintainer reported that the Acoustica 10.4 line was exercised successfully on a real Home Assistant OS installation. The repository does not currently record the exact Home Assistant OS version, machine architecture, microphone model, or individual steps from that session, so those details are not inferred here.

This manual evidence complements, but does not replace, the automated repository and image checks.

## Automated checks

Every pull request and push to `main` runs:

- Python compilation and the full pytest suite;
- YAML, JSON, shell, and JavaScript checks;
- exact dependency-lock validation;
- Home Assistant app linting;
- an amd64 Home Assistant image build;
- an aarch64 Home Assistant image build.

## Manual release checklist

Record the following for future release candidates:

- Home Assistant OS and Core versions;
- host architecture and hardware model;
- microphone model and selected input index;
- fresh installation or upgrade source version;
- add-on install and startup result;
- ingress tuner load and host-microphone recording;
- smoke/CO preset detection using a safe physical test control;
- saved profile activation and disable behavior;
- microphone hot switch and automatic rollback on an invalid device;
- Home Assistant discovery, confirmation, entity state, heartbeat recovery, and unload/reload;
- legacy profile migration and add-on backup/restore.

Do not use Acoustica as a substitute for certified life-safety alarms.
