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

    assert "COPY requirements.txt constraints.txt ./" in dockerfile
    assert "-c constraints.txt -r requirements.txt" in dockerfile
    assert workflow["jobs"]["validate"]["steps"][3]["run"].endswith(
        "-r acoustica/requirements-dev.txt"
    )


def test_ci_builds_validated_64_bit_architectures() -> None:
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
    )
    include = workflow["jobs"]["build"]["strategy"]["matrix"]["include"]

    assert {item["arch"] for item in include} == {"amd64", "aarch64"}
    assert all(item["build_from"].startswith("ghcr.io/home-assistant/") for item in include)
