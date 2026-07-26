from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from detector import __version__

ROOT = Path(__file__).parents[1]


def test_release_versions_match() -> None:
    config_version = yaml.safe_load(
        (ROOT / "config.yaml").read_text(encoding="utf-8")
    )["version"]
    manifest_version = json.loads(
        (ROOT / "custom_components" / "acoustica" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["version"]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    docker_version = re.search(r'io\.hass\.version="([^"]+)"', dockerfile)

    assert docker_version is not None
    assert {
        str(config_version),
        str(manifest_version),
        docker_version.group(1),
        __version__,
    } == {"10.5.0"}


def test_image_packages_runtime_control_assets() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY tuner/ ./tuner/" in dockerfile
    assert "COPY detector/ ./detector/" in dockerfile


def test_manifest_and_addon_declare_discovery() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    manifest = json.loads(
        (ROOT / "custom_components" / "acoustica" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert config["discovery"] == ["acoustica"]
    assert manifest["domain"] == "acoustica"
    assert manifest["config_flow"] is True
