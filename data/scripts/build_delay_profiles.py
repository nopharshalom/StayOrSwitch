#!/usr/bin/env python3
"""Build October time-conditioned profiles and freeze development-only estimates."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.delay_profiles.build import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "data/config/october.json")
    parser.add_argument("--directory", type=Path, default=ROOT / "data/processed/october")
    parser.add_argument("--dates", help="Comma-separated subset, only allowed with --smoke.")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    build(args.config, args.directory, dates=args.dates.split(",") if args.dates else None, smoke=args.smoke)


if __name__ == "__main__":
    main()
