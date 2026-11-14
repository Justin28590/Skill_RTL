#!/usr/bin/env python3
"""Repository-local entry point; no pip dependencies required."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rtlflow.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
