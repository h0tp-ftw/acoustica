"""Ingress wrapper around the pinned acoustic-engine tuner application."""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

import numpy as np
from acoustic_engine.input.listener import list_input_devices
from acoustic_engine.profiles import validate_profile
from acoustic_engine.tuner import validate as engine_tuner
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from detector.setup_service import (
    apply_tolerance,
    atomic_save_profile,
    atomic_write_text,
    audio_level,
    learn_profile,
    profile_summary,
    profile_to_yaml,
)

CONTROL_URL = os.getenv("ACOUSTICA_CONTROL_URL", "http://127.0.0.1:8100").rstrip("/")
ASSET_DIR = Path(__file__).parents[1] / "tuner"
_UNSAFE_PROFILE = re.compile(r"[^A-Za-z0-9_.-]+")
_RECORDING_LOCK = threading.Lock()

app = FastAPI(title="Acoustica Tuner")


class ActivationRequest(BaseModel):
    profile_id: str
    device_class: str = "sound"


class AudioSelectionRequest(BaseModel):
    device_index: int | None = None


class DisableRequest(BaseModel):
    source_kind: str
    source_value: str


class MicrophoneCheckRequest(BaseModel):
    seconds: float = Field(default=2.0, ge=1.0, le=5.0)
    device_index: int | None = None


class LearnSoundRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    seconds: float = Field(default=12.0, ge=4.0, le=30.0)
    tolerance: Literal["forgiving", "balanced", "precise"] = "balanced"
    device_index: int | None = None


class TuneProfileRequest(BaseModel):
    profile_yaml: str = Field(min_length=1, max_length=100_000)
    tolerance: Literal["forgiving", "balanced", "precise"]


class TestSoundRequest(BaseModel):
    profile_yaml: str = Field(min_length=1, max_length=100_000)
    seconds: float = Field(default=10.0, ge=3.0, le=30.0)
    device_index: int | None = None


class SaveAndEnableRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    profile_yaml: str = Field(min_length=1, max_length=100_000)
    device_class: str = Field(default="sound", min_length=1, max_length=40)


def _profiles_dir() -> Path:
    path = Path(os.getenv("ACOUSTIC_PROFILES_DIR", "/data/profiles"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_profile_stem(name: str) -> str:
    stem = _UNSAFE_PROFILE.sub("_", (name or "").strip()).strip("._")
    return (stem or "profile")[:100]


def _clean_detector_name(name: str) -> str:
    cleaned = " ".join(name.strip().split())
    if not cleaned:
        raise HTTPException(status_code=400, detail="Give this sound a name first.")
    return cleaned


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


def _current_audio_settings() -> tuple[int, int | None]:
    status = _runtime_request("GET", "/status")
    audio = status.get("audio") if isinstance(status.get("audio"), dict) else {}
    sample_rate_value = audio.get("sample_rate")
    device_value = audio.get("device_index")
    sample_rate = int(sample_rate_value) if isinstance(sample_rate_value, int) else 44100
    device_index = int(device_value) if isinstance(device_value, int) else None
    return sample_rate, device_index


def _record_audio(
    seconds: float,
    sample_rate: int,
    device_index: int | None,
) -> np.ndarray:
    if not _RECORDING_LOCK.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="Another microphone recording is already in progress.",
        )
    try:
        try:
            samples = engine_tuner._record_int16(seconds, sample_rate, device_index)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Microphone recording failed: {exc}",
            ) from None
    finally:
        _RECORDING_LOCK.release()

    if samples.size == 0:
        raise HTTPException(
            status_code=503,
            detail="No audio was captured. Check the microphone and try again.",
        )
    return samples.astype(np.int16, copy=False)


def _parse_profile(profile_yaml: str):
    try:
        profile = engine_tuner.parse_profile_from_yaml(profile_yaml)
        validate_profile(profile)
        return profile
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid detector pattern: {exc}",
        ) from None


def _test_guidance(
    *,
    detected: bool,
    tone_events: int,
    level: dict[str, object],
) -> dict[str, str]:
    level_status = str(level.get("status", "unknown"))
    if level_status in {"silent", "quiet"}:
        return {
            "code": "microphone_quiet",
            "title": "The test recording was too quiet",
            "message": "Move the microphone closer, play the sound louder, and test again.",
        }
    if level_status == "clipping":
        return {
            "code": "microphone_clipping",
            "title": "The test recording was too loud",
            "message": "Move the microphone farther away so the sound is clear instead of distorted.",
        }
    if detected:
        return {
            "code": "matched",
            "title": "Acoustica recognized it",
            "message": "This detector is ready to save and start listening.",
        }
    if tone_events == 0:
        return {
            "code": "no_tones",
            "title": "No repeating tones were found",
            "message": "Try another teaching recording with the sound played three to five times and less background noise.",
        }
    return {
        "code": "pattern_missed",
        "title": "The sound was heard, but the pattern did not match",
        "message": "Choose Forgiving matching, or record the teaching sample again with more repetitions.",
    }


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


@app.post("/api/acoustica/setup/microphone-check")
def setup_microphone_check(body: MicrophoneCheckRequest) -> dict[str, object]:
    """Record a short sample and report a plain-language microphone level."""

    sample_rate, current_device = _current_audio_settings()
    device_index = body.device_index if body.device_index is not None else current_device
    samples = _record_audio(body.seconds, sample_rate, device_index)
    return {
        "sample_rate": sample_rate,
        "device_index": device_index,
        **audio_level(samples),
    }


@app.post("/api/acoustica/setup/learn")
def setup_learn_sound(body: LearnSoundRequest) -> dict[str, object]:
    """Record several repetitions and learn a canonical detector profile."""

    sample_rate, current_device = _current_audio_settings()
    device_index = body.device_index if body.device_index is not None else current_device
    samples = _record_audio(body.seconds, sample_rate, device_index)
    level = audio_level(samples)
    if level["status"] == "silent":
        raise HTTPException(status_code=400, detail=str(level["message"]))

    try:
        profile = learn_profile(
            samples,
            sample_rate,
            name=_clean_detector_name(body.name),
            tolerance=body.tolerance,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not learn this sound: {exc}",
        ) from None

    return {
        "profile_yaml": profile_to_yaml(profile),
        "summary": profile_summary(profile),
        "microphone": level,
        "tolerance": body.tolerance,
    }


@app.post("/api/acoustica/setup/tune")
def setup_tune_profile(body: TuneProfileRequest) -> dict[str, object]:
    """Apply one understandable tolerance choice to a learned base profile."""

    profile = _parse_profile(body.profile_yaml)
    try:
        tuned = apply_tolerance(profile, body.tolerance)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "profile_yaml": profile_to_yaml(tuned),
        "summary": profile_summary(tuned),
        "tolerance": body.tolerance,
    }


@app.post("/api/acoustica/setup/test")
def setup_test_sound(body: TestSoundRequest) -> dict[str, object]:
    """Record a fresh sample and test it through the real detector pipeline."""

    profile = _parse_profile(body.profile_yaml)
    sample_rate, current_device = _current_audio_settings()
    device_index = body.device_index if body.device_index is not None else current_device
    samples = _record_audio(body.seconds, sample_rate, device_index)
    level = audio_level(samples)
    try:
        results = engine_tuner.run_engine_pipeline(samples, sample_rate, profile)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not test this sound: {exc}") from None

    detections = results.get("detections", [])
    tone_events = results.get("tone_events", [])
    detected = bool(detections)
    return {
        "detected": detected,
        "detection_count": len(detections),
        "tone_event_count": len(tone_events),
        "microphone": level,
        "guidance": _test_guidance(
            detected=detected,
            tone_events=len(tone_events),
            level=level,
        ),
        "details": results,
    }


@app.post("/api/acoustica/setup/save-and-enable")
def setup_save_and_enable(body: SaveAndEnableRequest) -> dict[str, object]:
    """Atomically save one learned profile and enable it in the live runtime."""

    profile = _parse_profile(body.profile_yaml)
    profile.name = _clean_detector_name(body.name)
    validate_profile(profile)
    profile_id = _safe_profile_stem(profile.name).lower()
    path = _profiles_dir() / f"{profile_id}.yaml"
    previous_text = path.read_text(encoding="utf-8") if path.is_file() else None
    atomic_save_profile(profile, path)

    try:
        runtime = _runtime_request(
            "POST",
            "/activate",
            {
                "profile_id": profile_id,
                "device_class": body.device_class,
            },
        )
    except Exception:
        if previous_text is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write_text(path, previous_text)
        raise

    return {
        "saved": True,
        "profile_id": profile_id,
        "detector_name": profile.name,
        "path": path.name,
        "runtime": runtime,
    }


@app.post("/api/acoustica/detectors/disable")
def disable_detector(body: DisableRequest) -> dict[str, Any]:
    """Disable one live detector source without restarting the add-on."""

    return _runtime_request(
        "POST",
        "/disable",
        {
            "source_kind": body.source_kind,
            "source_value": body.source_value,
        },
    )


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
