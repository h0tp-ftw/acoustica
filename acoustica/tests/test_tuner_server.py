from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from detector import tuner_server


def _request(*, ingress_path: str = "") -> Request:
    headers = []
    if ingress_path:
        headers.append((b"x-ingress-path", ingress_path.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8099),
            "root_path": "",
        }
    )


def test_tuner_shell_injects_ingress_controls(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<html><head></head><body><main>Engine tuner</main></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(tuner_server, "_engine_static_dir", lambda: tmp_path)

    response = tuner_server.tuner_index(
        _request(ingress_path="/api/hassio_ingress/example")
    )
    html = response.body.decode("utf-8")

    assert '<base href="/api/hassio_ingress/example/">' in html
    assert 'href="acoustica-controls.css"' in html
    assert 'src="acoustica-controls.js"' in html
    assert "Engine tuner" in html


def test_active_profile_cannot_be_deleted(monkeypatch, tmp_path: Path) -> None:
    profile = tmp_path / "hallway.yaml"
    profile.write_text("name: Hallway\nsegments: []\n", encoding="utf-8")
    monkeypatch.setenv("ACOUSTIC_PROFILES_DIR", str(tmp_path))
    monkeypatch.setattr(
        tuner_server,
        "_runtime_request",
        lambda *_args, **_kwargs: {
            "detectors": [
                {
                    "name": "Hallway",
                    "source_kind": "profile",
                    "source_value": "hallway.yaml",
                }
            ]
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        tuner_server.delete_profile("hallway")

    assert exc_info.value.status_code == 409
    assert profile.exists()


def test_inactive_profile_deletes_from_addon_storage(monkeypatch, tmp_path: Path) -> None:
    profile = tmp_path / "washer.yaml"
    profile.write_text("name: Washer\nsegments: []\n", encoding="utf-8")
    monkeypatch.setenv("ACOUSTIC_PROFILES_DIR", str(tmp_path))
    monkeypatch.setattr(
        tuner_server,
        "_runtime_request",
        lambda *_args, **_kwargs: {"detectors": []},
    )

    assert tuner_server.delete_profile("washer") == {"deleted": "washer"}
    assert not profile.exists()


def test_disable_detector_forwards_source_identity(monkeypatch) -> None:
    calls = []

    def fake_runtime_request(method, path, payload=None):
        calls.append((method, path, payload))
        return {"disabled": True}

    monkeypatch.setattr(tuner_server, "_runtime_request", fake_runtime_request)

    result = tuner_server.disable_detector(
        tuner_server.DisableRequest(
            source_kind="profile",
            source_value="hallway.yaml",
        )
    )

    assert result == {"disabled": True}
    assert calls == [
        (
            "POST",
            "/disable",
            {"source_kind": "profile", "source_value": "hallway.yaml"},
        )
    ]


def test_audio_devices_include_current_runtime_selection(monkeypatch) -> None:
    monkeypatch.setattr(
        tuner_server,
        "list_input_devices",
        lambda: [
            {
                "index": 4,
                "name": "USB microphone",
                "channels": 1,
                "default": True,
                "backend": "sounddevice",
            }
        ],
    )
    monkeypatch.setattr(
        tuner_server,
        "_runtime_request",
        lambda *_args, **_kwargs: {"audio": {"device_index": 4}},
    )

    assert tuner_server.audio_devices() == {
        "current_index": 4,
        "devices": [
            {
                "index": 4,
                "name": "USB microphone",
                "channels": 1,
                "default": True,
                "backend": "sounddevice",
            }
        ],
    }


def test_custom_routes_precede_engine_mount() -> None:
    paths = [getattr(route, "path", None) for route in tuner_server.app.routes]
    mount_index = paths.index("") if "" in paths else paths.index("/")
    assert paths.index("/api/acoustica/status") < mount_index
    assert paths.index("/api/acoustica/detectors/disable") < mount_index
    assert paths.index("/") < mount_index or paths.index("/") == mount_index
