from __future__ import annotations

from pathlib import Path

from detector.yaml_loader import load_profile_from_yaml, save_profile_to_yaml


def test_engine_profile_schema_round_trips(tmp_path: Path) -> None:
    source = Path("profiles/smoke_alarm_t3.yaml")
    profile = load_profile_from_yaml(source)
    destination = tmp_path / "profile.yaml"

    save_profile_to_yaml(profile, destination)
    restored = load_profile_from_yaml(destination)

    assert restored == profile
