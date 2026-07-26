from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = ROOT.parent


def _requirements(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_runtime_dependencies_are_exactly_locked() -> None:
    requirements = _requirements(ROOT / "requirements.txt")
    constraints = _requirements(ROOT / "constraints.txt")

    engine = requirements[0]
    assert re.search(r"@[0-9a-f]{40}$", engine)
    assert all("==" in item for item in requirements[1:])
    assert all("==" in item for item in constraints)
    assert not any(">=" in item or "~=" in item for item in requirements + constraints)


def test_docker_and_ci_use_the_same_constraints() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
    )

    assert "ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.21" in dockerfile
    assert "COPY requirements.txt constraints.txt ./" in dockerfile
    assert "-c constraints.txt -r requirements.txt" in dockerfile
    assert workflow["jobs"]["validate"]["steps"][3]["run"].endswith(
        "-r acoustica/requirements-dev.txt"
    )


def test_manifest_uses_current_home_assistant_app_contract() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    build = yaml.safe_load((ROOT / "build.yaml").read_text(encoding="utf-8"))
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    startup = (ROOT / "run.sh").read_text(encoding="utf-8")
    apparmor = (ROOT / "apparmor.txt").read_text(encoding="utf-8")

    assert config["arch"] == ["aarch64", "amd64"]
    assert set(build["build_from"]) == {"aarch64", "amd64"}
    assert "startup" not in config
    assert "boot" not in config
    assert "ingress_port" not in config
    assert config["map"] == ["homeassistant_config:rw"]
    assert 'io.hass.arch="aarch64|amd64"' in dockerfile
    assert "/homeassistant/custom_components/acoustica" in startup
    assert "/config/custom_components" not in startup
    assert "/config/**" not in apparmor


def test_ci_builds_validated_64_bit_architectures() -> None:
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
    )
    include = workflow["jobs"]["build"]["strategy"]["matrix"]["include"]

    assert {item["arch"] for item in include} == {"amd64", "aarch64"}
    assert all(item["build_from"].startswith("ghcr.io/home-assistant/") for item in include)
    assert "browser" in workflow["jobs"]["build"]["needs"]


def test_ci_runs_the_real_beginner_browser_flow() -> None:
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
    )
    browser = workflow["jobs"]["browser"]
    script = browser["steps"][1]["run"]

    assert browser["name"] == "Beginner browser flow"
    assert "google-chrome" in script
    assert "easy_setup_harness.html" in script
    assert 'data-status="passed"' in script
