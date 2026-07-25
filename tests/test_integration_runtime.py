from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _load_runtime_class():
    root = Path("custom_components/acoustic_alarm_detector")
    package_name = "acoustic_alarm_detector_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(root)]
    sys.modules[package_name] = package

    for module_name in ("const", "runtime"):
        spec = importlib.util.spec_from_file_location(
            f"{package_name}.{module_name}",
            root / f"{module_name}.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

    return sys.modules[f"{package_name}.runtime"].DetectorRuntime


def test_runtime_accepts_matching_versioned_state_and_can_expire() -> None:
    runtime_class = _load_runtime_class()
    runtime = runtime_class(
        detector_id="hallway", profile_id="smoke", alarm_type="smoke"
    )

    assert runtime.apply_event(
        {
            "protocol_version": 1,
            "detector_id": "hallway",
            "profile_id": "smoke",
            "active": True,
            "updated_at": "2026-07-25T12:00:00+00:00",
            "source_version": "9.5.0",
        }
    ) is True
    assert runtime.active is True
    assert runtime.available is True
    assert runtime.mark_unavailable() is True
    assert runtime.available is False
    assert runtime.mark_unavailable() is False


def test_runtime_rejects_wrong_profile_without_mutating_state() -> None:
    runtime_class = _load_runtime_class()
    runtime = runtime_class(
        detector_id="hallway", profile_id="smoke", alarm_type="smoke"
    )

    assert runtime.apply_event(
        {
            "protocol_version": 1,
            "detector_id": "hallway",
            "profile_id": "co",
            "active": True,
        }
    ) is False
    assert runtime.active is False
    assert runtime.available is False
