from __future__ import annotations

from pathlib import Path

_COMPONENT = Path(__file__).parents[1] / "custom_components" / "acoustica"


def test_config_flow_supports_confirmed_supervisor_discovery() -> None:
    source = (_COMPONENT / "config_flow.py").read_text(encoding="utf-8")

    assert "async def async_step_hassio" in source
    assert "discovery_info.uuid" in source
    assert "async_step_hassio_confirm" in source
    assert "self.async_show_form(" in source
    assert 'step_id="hassio_confirm"' in source


def test_config_flow_keeps_single_instance_manual_fallback() -> None:
    source = (_COMPONENT / "config_flow.py").read_text(encoding="utf-8")
    manifest = (_COMPONENT / "manifest.json").read_text(encoding="utf-8")

    assert "async def async_step_user" in source
    assert "single_instance_allowed" in source
    assert '"single_config_entry": true' in manifest
