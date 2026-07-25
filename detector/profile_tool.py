"""Command-line backend for learning and managing canonical alarm profiles."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from acoustic_engine.profiles import load_profile_from_yaml, validate_profile

from .profile_service import ProfileStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Learn and manage Acoustic Alarm Detector profiles"
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help="Profile directory (default: PROFILE_DIR or /data/profiles)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze", help="Analyze a PCM WAV without saving it"
    )
    analyze.add_argument("recording", type=Path)
    analyze.add_argument("--id", required=True, dest="profile_id")

    learn = subparsers.add_parser("learn", help="Analyze and save a PCM WAV profile")
    learn.add_argument("recording", type=Path)
    learn.add_argument("--id", required=True, dest="profile_id")
    learn.add_argument("--overwrite", action="store_true")
    learn.add_argument(
        "--accept-review",
        action="store_true",
        help="Save a profile whose recording quality needs review",
    )

    import_parser = subparsers.add_parser(
        "import", help="Import a canonical acoustic-engine YAML profile"
    )
    import_parser.add_argument("profile", type=Path)
    import_parser.add_argument("--id", dest="profile_id")
    import_parser.add_argument("--overwrite", action="store_true")

    subparsers.add_parser("list", help="List saved profiles")

    show = subparsers.add_parser("show", help="Print one saved profile YAML")
    show.add_argument("profile_id")

    delete = subparsers.add_parser("delete", help="Delete one saved profile")
    delete.add_argument("profile_id")

    validate = subparsers.add_parser("validate", help="Validate an engine YAML profile")
    validate.add_argument("profile", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ProfileStore(args.profile_dir)

    try:
        if args.command == "analyze":
            result = store.analyze(args.recording, args.profile_id)
            print(json.dumps(result.as_dict(), indent=2))
            return 0

        if args.command == "learn":
            result = store.learn(
                args.recording,
                args.profile_id,
                overwrite=args.overwrite,
                accept_review=args.accept_review,
            )
            payload = result.as_dict()
            payload["path"] = str(store.path_for(result.profile_id))
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "import":
            destination = store.import_profile(
                args.profile,
                profile_id=args.profile_id,
                overwrite=args.overwrite,
            )
            print(json.dumps({"path": str(destination), "profile_id": destination.stem}))
            return 0

        if args.command == "list":
            print(json.dumps([asdict(item) for item in store.list()], indent=2))
            return 0

        if args.command == "show":
            print(store.path_for(args.profile_id).read_text(encoding="utf-8"), end="")
            return 0

        if args.command == "delete":
            deleted = store.delete(args.profile_id)
            print(json.dumps({"deleted": deleted, "profile_id": args.profile_id}))
            return 0 if deleted else 1

        if args.command == "validate":
            profile = load_profile_from_yaml(args.profile)
            validate_profile(profile)
            print(
                json.dumps(
                    {
                        "valid": True,
                        "name": profile.name,
                        "segments": len(profile.segments),
                    },
                    indent=2,
                )
            )
            return 0

    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
