#!/usr/bin/env python3
"""Train component models on development dates and freeze before final testing."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "algo"))

from stayorswitch.model_training.pipeline import train


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "algo/config/model-training.json")
    args = parser.parse_args()
    train(args.config)


if __name__ == "__main__":
    main()
