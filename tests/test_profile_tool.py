from __future__ import annotations

import json
from pathlib import Path

from detector.profile_tool import main


def test_profile_tool_lists_empty_store(tmp_path: Path, capsys) -> None:
    assert main(["--profile-dir", str(tmp_path), "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_profile_tool_validates_canonical_profile(capsys) -> None:
    assert main(["validate", "profiles/smoke_alarm_t3.yaml"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["valid"] is True
    assert output["segments"] == 6
