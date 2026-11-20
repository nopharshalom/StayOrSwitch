#!/usr/bin/env python3
"""Verify or score the final weekday-only November peak-delay analysis."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.november_weekday_peaks import score, verify_selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        _, rows, _ = verify_selection()
        print({"stage": "WEEKDAY_SELECTION_VERIFIED", "rows": len(rows)})
    else:
        score()


if __name__ == "__main__":
    main()
