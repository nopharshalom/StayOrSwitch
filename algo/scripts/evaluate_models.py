#!/usr/bin/env python3
"""Evaluate the unchanged frozen component experiment on final-test dates."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "algo"))

from stayorswitch.model_training.pipeline import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, default=ROOT / "algo/models/pilot-v1/frozen.json")
    args = parser.parse_args()
    evaluate(args.frozen)


if __name__ == "__main__":
    main()
