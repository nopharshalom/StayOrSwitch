#!/usr/bin/env python3
"""Preserve the input-only November source manifest before label preparation."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "algo")]

from data.october.sources import sha256


def freeze_inputs(source, destination):
    source, destination = Path(source), Path(destination)
    payload = source.read_bytes()
    value = json.loads(payload)
    if value.get("stage") != "INPUTS_PREPARED" or any(key in value for key in ("labels", "daily_labels")):
        raise ValueError("Only an input-only prepared manifest may be frozen.")
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError("The existing input freeze must not be overwritten.")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(payload)
    return sha256(destination)


if __name__ == "__main__":
    target = ROOT / "data/manifests/november-2026-inputs.json"
    digest = freeze_inputs(ROOT / "data/manifests/november-2026.json", target)
    print(json.dumps({"input_manifest": str(target.relative_to(ROOT)), "sha256": digest}))
