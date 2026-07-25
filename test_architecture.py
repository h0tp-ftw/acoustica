#!/usr/bin/env python3
"""Compatibility entry point for the repository test suite.

The project now has one test runner: pytest. This wrapper keeps the old
`python test_architecture.py` command useful without maintaining a second set
of architecture checks.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    return subprocess.call([sys.executable, "-m", "pytest"])


if __name__ == "__main__":
    raise SystemExit(main())
