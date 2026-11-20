#!/usr/bin/env python3
"""Build a new full-October model without changing the existing experiment."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.full_october_fit import build_full_october


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "data/config/full-october-fit.json")
    parser.add_argument("--november-directory", type=Path, default=ROOT / "data/processed/november-2026")
    args = parser.parse_args()
    build_full_october(args.config, args.november_directory)


if __name__ == "__main__":
    main()
