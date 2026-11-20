#!/usr/bin/env python3
"""Prepare and score the fixed November daily peak ETA analysis separately."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.november_peak_analysis import prepare, score, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare-inputs", action="store_true")
    group.add_argument("--score", action="store_true")
    group.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_inputs:
        prepare()
    elif args.score:
        score()
    else:
        prepared = verify()
        print({"stage": "VERIFIED", "rows": len(prepared["rows"])})


if __name__ == "__main__":
    main()
