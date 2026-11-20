#!/usr/bin/env python3
"""Acquire and prepare the isolated November 1–19 follow-up source package."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.november_2026 import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--inputs-only", action="store_true")
    group.add_argument("--labels-only", action="store_true")
    group.add_argument("--download-only", action="store_true")
    parser.add_argument("--process-only", action="store_true")
    args = parser.parse_args()
    prepare(**vars(args))


if __name__ == "__main__":
    main()
