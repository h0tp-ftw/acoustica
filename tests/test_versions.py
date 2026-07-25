from __future__ import annotations

import json
import re
import runpy
from pathlib import Path

import yaml

from detector import __version__


def test_addon_and_integration_versions_stay_aligned() -> None:
    addon = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    manifest = json.loads(
        Path("custom_components/acoustic_alarm_detector/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    integration = runpy.run_path(
        "custom_components/acoustic_alarm_detector/const.py"
    )
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    docker_version = re.search(r'io\.hass\.version="([^"]+)"', dockerfile)

    assert docker_version is not None
    assert {
        addon["version"],
        manifest["version"],
        integration["VERSION"],
        docker_version.group(1),
        __version__,
    } == {"9.5.0"}
