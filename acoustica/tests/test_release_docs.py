from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_home_assistant_release_documents_exist() -> None:
    for name in ("README.md", "DOCS.md", "CHANGELOG.md", "QUICKSTART.md"):
        path = ROOT / name
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip()


def test_changelog_records_runtime_and_haos_validation() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "## 10.4.0" in changelog
    assert "automatic" in changelog.lower()
    assert "Home Assistant OS" in changelog
    assert "amd64" in changelog and "aarch64" in changelog


def test_config_comments_describe_current_storage() -> None:
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")

    assert "/data/profiles" in config
    assert "/data/sounds" in config
    assert "Compatibility only" in config
