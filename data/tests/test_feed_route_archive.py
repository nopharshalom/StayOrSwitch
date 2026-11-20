"""Selection-view causality and strict selected-outcome separation checks."""

from copy import deepcopy
import unittest

from data.feed_route_archive import FeedRouteArchive
from data.route_archive import build_from_snapshots
from data.tests.test_route_archive import BASE, LEG, TEMPLATE, labels_for, snapshot, trip


def payload(snapshots, labels=None, templates=None):
    return build_from_snapshots(snapshots, templates or [TEMPLATE], labels or {})


def views(archive, ready=10, horizon=120, leg=None):
    return list(archive.frames_for(leg or LEG, BASE + ready, BASE + horizon))


class FeedRouteArchiveTests(unittest.TestCase):
    def test_latest_initial_capture_then_only_later_captures(self):
        value = trip()
        archive = FeedRouteArchive(payload([snapshot(0, [value]), snapshot(60, [value]),
                                             snapshot(120, [value]), snapshot(180, [value])]))
        frames = views(archive, ready=70, horizon=130)
        self.assertEqual([f["at"] for f in frames], [BASE + 60, BASE + 120])
        self.assertEqual(frames[-1]["next_capture_at"], BASE + 180)

    def test_equal_capture_is_asof_not_a_duplicate_update(self):
        value = trip()
        archive = FeedRouteArchive(payload([snapshot(0, [value]), snapshot(60, [value])]))
        self.assertEqual([f["at"] for f in views(archive, ready=60)], [BASE + 60])

    def test_omitted_train_not_carried_to_new_full_capture(self):
        value = trip()
        archive = FeedRouteArchive(payload([snapshot(0, [value]), snapshot(60, [])]))
        frames = views(archive)
        self.assertEqual(len(frames[0]["candidates"]), 1)
        self.assertEqual(frames[1]["candidates"], [])

    def test_train_not_visible_until_its_observation_capture(self):
        first = trip()
        later = trip(route="C")
        templates = [TEMPLATE, dict(TEMPLATE, id="c", legs=[dict(LEG, route_id="C")])]
        archive = FeedRouteArchive(payload([snapshot(0, [first]), snapshot(60, [first, later])],
                                            templates=templates))
        frames = views(archive, leg=dict(LEG, route_ids=["A", "C"]))
        self.assertEqual([c["route_id"] for c in frames[0]["candidates"]], ["A"])
        self.assertEqual([c["route_id"] for c in frames[1]["candidates"]], ["A", "C"])

    def test_unusable_current_frame_does_not_reuse_older_good_candidates(self):
        value = trip()
        archive = FeedRouteArchive(payload([snapshot(0, [value]), snapshot(60, [value], status="MISSING")]))
        frame = views(archive, ready=70)[0]
        self.assertFalse(frame["eligible"])
        self.assertEqual(frame["at"], BASE + 60)
        self.assertEqual(frame["candidates"], [])

    def test_outcome_quality_and_final_times_do_not_change_views(self):
        value = trip()
        original = payload([snapshot(0, [value]), snapshot(60, [value])], labels_for(value))
        altered = deepcopy(original)
        event = altered["events"][0]
        event.update(departure_at=None, arrival_at=BASE + 5000,
                     endpoint_flags={"boarding": ["BAD_DEPARTURE"], "alighting": []})
        self.assertEqual(views(FeedRouteArchive(original)), views(FeedRouteArchive(altered)))

    def test_candidate_with_missing_labels_remains_visible(self):
        value = trip()
        archive = FeedRouteArchive(payload([snapshot(0, [value])]))
        candidate = views(archive)[0]["candidates"][0]
        self.assertEqual(candidate["path_status"], "COMPATIBLE")
        self.assertEqual(candidate["departure_forecast_at"], BASE + 100)
        outcome = archive.event_for(LEG, candidate["event_key"])
        self.assertIsNone(outcome["departure_at"])
        self.assertIn("MISSING_LABEL_RECORD", outcome["endpoint_flags"]["boarding"])

    def test_selection_view_has_no_final_endpoint_or_future_alias_fields(self):
        value = trip()
        archive = FeedRouteArchive(payload([snapshot(0, [value])], labels_for(value)))
        candidate = views(archive)[0]["candidates"][0]
        forbidden = {"departure_at", "arrival_at", "endpoint_flags", "endpoint_evidence",
                     "trip_aliases", "observations", "first_observed_at", "last_observed_at"}
        self.assertFalse(set(candidate).intersection(forbidden))

    def test_current_observed_alias_is_used_not_a_future_alias(self):
        first = trip(start_time="00:01:00")
        second = trip(start_time="00:02:00")
        archive = FeedRouteArchive(payload([snapshot(0, [first]), snapshot(60, [second])],
                                            {**labels_for(first), **labels_for(second)}))
        frames = views(archive)
        self.assertEqual(frames[0]["candidates"][0]["trip_id"], first["id"])
        self.assertEqual(frames[1]["candidates"][0]["trip_id"], second["id"])
        self.assertEqual(frames[0]["candidates"][0]["event_key"], frames[1]["candidates"][0]["event_key"])

    def test_simultaneous_alias_ambiguity_is_not_rehabilitated(self):
        first = trip(start_time="00:01:00")
        second = trip(start_time="00:02:00")
        archive = FeedRouteArchive(payload([snapshot(0, [first, second]), snapshot(60, [first])],
                                            {**labels_for(first), **labels_for(second)}))
        frames = views(archive)
        self.assertEqual(frames[0]["candidates"][0]["path_status"], "UNKNOWN")
        self.assertIsNone(frames[0]["candidates"][0]["departure_forecast_at"])
        self.assertEqual(frames[1]["candidates"][0]["path_status"], "COMPATIBLE")

    def test_explicit_empty_stop_cancellation_is_a_current_observation(self):
        value = trip()
        canceled = dict(value, schedule_relationship="CANCELED", stop_updates=[])
        archive = FeedRouteArchive(payload([snapshot(0, [value]), snapshot(60, [canceled]), snapshot(120, [])]))
        frames = views(archive)
        self.assertEqual(frames[1]["candidates"][0]["explicit_terminal_state"], "CANCELED")
        self.assertEqual(frames[1]["candidates"][0]["path_status"], "INCOMPATIBLE")
        self.assertEqual(frames[2]["candidates"], [])

    def test_unknown_feed_returns_explicit_missing_initial_frame(self):
        archive = FeedRouteArchive(payload([]))
        frame = views(archive)[0]
        self.assertEqual(frame["reason"], "NO_CAPTURE_AT_OR_BEFORE_READINESS")
        self.assertFalse(frame["eligible"])

    def test_missing_initial_frame_does_not_backdate_later_feed(self):
        value = trip()
        archive = FeedRouteArchive(payload([snapshot(60, [value])]))
        frames = views(archive)
        self.assertTrue(frames[0]["is_synthetic_missing_frame"])
        self.assertEqual(frames[0]["candidates"], [])
        self.assertEqual(frames[1]["at"], BASE + 60)

    def test_query_does_not_mutate_cached_observations_or_outcomes(self):
        value = trip()
        data = payload([snapshot(0, [value])], labels_for(value))
        before = deepcopy(data)
        archive = FeedRouteArchive(data)
        candidate = views(archive)[0]["candidates"][0]
        candidate["reason_codes"].append("LOCAL_CHANGE")
        result = archive.event_for(LEG, candidate["event_key"])
        result["endpoint_flags"]["boarding"].append("LOCAL_CHANGE")
        self.assertEqual(data, before)

    def test_wrong_route_cannot_access_selected_outcome(self):
        value = trip()
        archive = FeedRouteArchive(payload([snapshot(0, [value])], labels_for(value)))
        event_key = views(archive)[0]["candidates"][0]["event_key"]
        with self.assertRaises(ValueError):
            archive.event_for(dict(LEG, route_id="C"), event_key)

    def test_invalid_or_reversed_query_rejected(self):
        archive = FeedRouteArchive(payload([]))
        for ready, end in ((BASE + 10, BASE), (True, BASE), (float("nan"), BASE), (BASE, float("inf"))):
            with self.subTest(ready=ready, end=end), self.assertRaises((ValueError, OverflowError)):
                list(archive.frames_for(LEG, ready, end))

    def test_bad_membership_interval_rejected(self):
        value = trip()
        data = payload([snapshot(0, [value]), snapshot(60, [value])])
        data["events"][0]["observations"][0]["valid_until_at"] = BASE + 120
        with self.assertRaises(ValueError):
            FeedRouteArchive(data)

    def test_duplicate_capture_or_event_rejected(self):
        value = trip()
        data = payload([snapshot(0, [value])])
        duplicate = deepcopy(data)
        duplicate["feed_records"]["ace"].append(duplicate["feed_records"]["ace"][0])
        with self.assertRaises(ValueError):
            FeedRouteArchive(duplicate)
        duplicate = deepcopy(data)
        duplicate["events"].append(duplicate["events"][0])
        with self.assertRaises(ValueError):
            FeedRouteArchive(duplicate)


if __name__ == "__main__":
    unittest.main()
