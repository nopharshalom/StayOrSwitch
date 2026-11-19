"""Conservative receipt bounds for hindsight journal outcome markers."""

from bisect import bisect_right
from collections import defaultdict

from .features import epoch, local_date, split_for_date


class LabelReceiptIndex:
    """Find a sampled collector receipt whose source has reached a journal marker.

    CSV marked_past timestamps are source-feed times, not collector receipt or
    CSV publication times. The first sampled source strictly after that marker is
    an upper bound on when this historical evidence had reached the collector.
    """

    def __init__(self):
        self.sources = defaultdict(list)
        self.captures = defaultdict(list)

    def add(self, snapshot):
        source = epoch(snapshot.get("source_updated_at"))
        captured = epoch(snapshot.get("captured_at", snapshot.get("fetched_at")))
        feed = snapshot.get("feed_id")
        if not feed or source is None or captured is None or source > captured:
            return
        if snapshot.get("status", "AVAILABLE") != "AVAILABLE":
            return
        sources = self.sources[feed]
        if sources and source <= sources[-1]:
            return
        if self.captures[feed] and captured < self.captures[feed][-1]:
            return
        sources.append(source)
        self.captures[feed].append(captured)

    def receipt(self, feed, marker):
        if marker is None:
            return None
        # Different payloads can share an integer source timestamp. Advancing
        # beyond the marker avoids treating the first such payload as final.
        index = bisect_right(self.sources[feed], marker)
        return self.captures[feed][index] if index < len(self.sources[feed]) else None

    def apply(self, row):
        label = row["label"]
        feed = row["features"]["feed_id"]
        markers = ([label.get("origin_available_at"), label.get("destination_available_at")]
                   if "origin_available_at" in label else [label.get("available_at")])
        bounds = [self.receipt(feed, marker) for marker in markers]
        confirmed = max(bounds) if bounds and all(bound is not None for bound in bounds) else None
        label["availability_source"] = "JOURNAL_SOURCE_TIME_WITH_SAMPLED_COLLECTOR_RECEIPT_BOUND"
        label["receipt_confirmed_at"] = confirmed
        label["receipt_bound_is_csv_publication_time"] = False
        flags = label.setdefault("quality_flags", [])
        if confirmed is None:
            flag = "NO_RAW_LABEL_RECEIPT_CONFIRMATION"
        elif split_for_date(local_date(confirmed)) != row["split"]:
            flag = "LABEL_RECEIPT_SPLIT_BOUNDARY"
        else:
            flag = None
        if flag:
            if flag not in flags:
                flags.append(flag)
            row["eligible_for_training"] = False
        return row
