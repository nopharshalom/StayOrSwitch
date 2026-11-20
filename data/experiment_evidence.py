"""Read the exact feed queries and vehicle observations used by the November replay."""
from collections import defaultdict
import gzip
import json
from pathlib import Path

INPUTS = Path(__file__).resolve().parent / "artifacts/november-two-corridor-replay.json.gz"


class ExperimentEvidence:
    def __init__(self, path=INPUTS):
        with gzip.open(path, "rt") as stream:
            data = json.load(stream)
        self.cases = data["cases"]
        self.routes = data["routes"]
        self.positions = data["positions"]
        self.decision_source_sha256 = data["decision_source_sha256"]
        self.frames = data["frames"]
        self.events = data["events"]

    def frames_for(self, leg, ready, horizon):
        query = json.dumps([leg, ready, horizon], sort_keys=True, separators=(",", ":"))
        return iter(self.frames[query])

    def event_for(self, leg, train):
        query = json.dumps([leg, train], sort_keys=True, separators=(",", ":"))
        if query not in self.events:
            raise RuntimeError("Train lookup is outside the frozen experiment inputs.")
        event = self.events[query]
        if event and event.get("identity_error"):
            raise ValueError("Selected train has an ambiguous archived identity.")
        return event


def stop_bounds(records, stop, max_gap=120):
    """Bracket the recorded stop visit using adjacent position observations."""
    by_time = defaultdict(set)
    for t, seq, station, status in records:
        by_time[t].add((seq, station, status))
    ordered = [
        (t, next(iter(obs)) if len(obs) == 1 and next(iter(obs))[2] != -2 else None)
        for t, obs in sorted(by_time.items())
    ]
    visits = [i for i, (_, obs) in enumerate(ordered) if obs and obs[1:] == (stop, 1)]
    if not visits:
        return {}
    first, last = visits[0], visits[-1]
    seq = ordered[first][1][0]
    if any(obs != (seq, stop, 1) for _, obs in ordered[first : last + 1]):
        return {}
    if any(obs and obs[1] == stop and obs[0] != seq for _, obs in ordered):
        return {}
    result = {}
    if first:
        t, obs = ordered[first - 1]
        if (
            obs
            and ordered[first][0] - t <= max_gap
            and (
                (obs[0] < seq and obs[1] != stop)
                or (obs[:2] == (seq, stop) and obs[2] in (0, 2))
            )
        ):
            result["arrival"] = (t, ordered[first][0])
    if last + 1 < len(ordered):
        t, obs = ordered[last + 1]
        if obs and t - ordered[last][0] <= max_gap and obs[0] > seq and obs[1] != stop:
            result["departure"] = (ordered[last][0], t)
    return result
