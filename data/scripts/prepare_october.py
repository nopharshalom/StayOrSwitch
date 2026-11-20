#!/usr/bin/env python3
"""Acquire and prepare the configured full October historical month."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.october.prepare import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "data/config/october.json")
    parser.add_argument("--dates", help="Comma-separated October dates for an explicitly partial smoke run.")
    parser.add_argument("--process-only", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    prepare(args.config, selected_dates=args.dates.split(",") if args.dates else None,
            process_only=args.process_only, download_only=args.download_only, workers=args.workers)


if __name__ == "__main__":
    main()
