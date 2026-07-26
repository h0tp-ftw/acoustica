"""Ingress wrapper around the pinned acoustic-engine tuner application."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from acoustic_engine.input.listener import list_input_devices
from acoustic_engine.tuner import validate as engine_tuner
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

CONTROL_URL = os.getenv("ACOUSTICA_CONTROL_URL", "http://127.0.0.1:8100").rstrip("/")
ASSET_DIR = Path(__file__).parents[1] / "tuner"
_UNSAFE_PROFILE = re.compile(r"[^A-Za-z0-9_.-]+")

app = FastAPI(title="Acoustica Tuner")


class ActivationRequest(BaseModel):
    profile_id: str
    device_class: str = "sound"


class AudioSelectionRequest(BaseModel):
    device_index: int | None = None


def _profiles_dir() -> Path:
    path = Path(os.getenv("ACOUSTIC_PROFILES_DIR", "/data/profiles"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_profile_stem(name: str) -> str:
    stem = _UNSAFE_PROFILE.sub("_", (name or "").strip()).strip("._")
    return (stem or "profile")[:100]


def _engine_static_dir() -> Path:
    default = Path(engine_tuner.__file__).resolve().parent / "static"
    return Path(os.getenv("ACOUSTIC_TUNER_STATIC", str(default)))


def _runtime_request(
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{CONTROL_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error")
        except Exception:
            detail = None
        raise HTTPException(status_code=exc.code, detail=detail or exc.reason) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Detector runtime is unavailable: {exc}",
        ) from None

    if not body:
        return {}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Runtime returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Runtime returned an invalid response")
    return parsed


@app.get("/api/acoustica/status")
def runtime_status() -> dict[str, Any]:
    """Return the detector process health snapshot."""

    return _runtime_request("GET", "/status")


@app.get("/api/acoustica/audio/devices")
def audio_devices() -> dict[str, object]:
    """List engine input devices and identify the current selection."""

    try:
        devices = [
            {
                "index": int(item["index"]),
                "name": str(item.get("name", "Unknown microphone")),
                "channels": int(item.get("channels", 0)),
                "default": bool(item.get("default", False)),
                "backend": str(item.get("backend", "unknown")),
            }
            for item in list_input_devices()
            if isinstance(item, dict) and "index" in item
        ]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not list microphones: {exc}") from None

    status = _runtime_request("GET", "/status")
    audio = status.get("audio") if isinstance(status.get("audio"), dict) else {}
    return {
        "current_index": audio.get("device_index"),
        "devices": devices,
    }


@app.post("/api/acoustica/audio/select")
def select_audio_device(body: AudioSelectionRequest) -> dict[str, Any]:
    """Persist and hot-reload one audio input device."""

    return _runtime_request(
        "POST",
        "/audio/select",
        {"device_index": body.device_index},
    )


@app.post("/api/acoustica/profiles/activate")
def activate_profile(body: ActivationRequest) -> dict[str, Any]:
    """Enable one saved engine profile in the live detector."""

    return _runtime_request(
        "POST",
        "/activate",
        {
            "profile_id": body.profile_id,
            "device_class": body.device_class,
        },
    )


@app.delete("/profiles/{name}")
def delete_profile(name: str) -> dict[str, str]:
    """Prevent deletion of a profile currently referenced by live options."""

    status = _runtime_request("GET", "/status")
    active_sources = {
        str(item.get("source_value"))
        for item in status.get("detectors", [])
        if isinstance(item, dict) and item.get("source_kind") == "profile"
    }
    safe_name = _safe_profile_stem(name)
    filename = f"{safe_name}.yaml"
    if filename in active_sources:
        raise HTTPException(
            status_code=409,
            detail="Disable this detector before deleting its active profile.",
        )

    path = _profiles_dir() / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"No profile named '{name}'")
    path.unlink()
    return {"deleted": safe_name}


@app.get("/acoustica-controls.js")
def controls_javascript() -> FileResponse:
    return FileResponse(ASSET_DIR / "acoustica-controls.js", media_type="text/javascript")


@app.get("/acoustica-controls.css")
def controls_stylesheet() -> FileResponse:
    return FileResponse(ASSET_DIR / "acoustica-controls.css", media_type="text/css")


@app.get("/", response_class=HTMLResponse)
def tuner_index(request: Request) -> HTMLResponse:
    """Serve the engine tuner shell with the Acoustica runtime panel injected."""

    index = _engine_static_dir() / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Tuner UI is not bundled")

    ingress = request.headers.get("X-Ingress-Path", "").rstrip("/")
    base = f"{ingress}/" if ingress else "/"
    html = index.read_text(encoding="utf-8")
    html = html.replace(
        "<head>",
        (
            "<head>\n"
            f'    <base href="{base}">\n'
            '    <link rel="stylesheet" href="acoustica-controls.css">'
        ),
        1,
    )
    html = html.replace(
        "</body>",
        '    <script defer src="acoustica-controls.js"></script>\n</body>',
        1,
    )
    return HTMLResponse(html)


# Keep every existing engine validation/recording/profile route and static asset.
# Custom routes above are registered first, so they win before this catch-all mount.
app.mount("/", engine_tuner.app, name="engine-tuner")


def main() -> None:
    parser = argparse.ArgumentParser(description="Acoustica ingress tuner")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--profiles-dir", default="/data/profiles")
    args = parser.parse_args()

    os.environ["ACOUSTIC_PROFILES_DIR"] = args.profiles_dir
    Path(args.profiles_dir).mkdir(parents=True, exist_ok=True)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
