#!/usr/bin/env python3
"""Preserve direct source evidence for one collapsed stop-time sequence."""
from pathlib import Path
import gzip
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
DAY = '2026-11-18'
TRIP = '035883_C..S05R'
CASE = 'portauthority_tandon--lmm-alert-276905--1795009883577'
manifest_path = ROOT / 'data/manifests/november-2026.json'
manifest = json.loads(manifest_path.read_text())
day = next(row for row in manifest['days'] if row['date'] == DAY)
source_specs = {'snapshots': day['outputs']['snapshots'], 'labels': manifest['daily_labels'][DAY]}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


for spec in source_specs.values():
    assert sha(ROOT / spec['path']) == spec['sha256']
labels = json.load(gzip.open(ROOT / source_specs['labels']['path'], 'rt'))
target_labels = {trip: stops for trip, stops in labels.items() if TRIP in trip}
timeline = []
post_last_capture = None
with gzip.open(ROOT / source_specs['snapshots']['path'], 'rt') as handle:
    for line in handle:
        snapshot = json.loads(line)
        if snapshot.get('feed_id') != 'ace':
            continue
        found = [trip for trip in snapshot.get('trips', []) if TRIP in trip.get('id', '')]
        for trip in found:
            stops = [{'stop_id': stop.get('stop_id'), 'arrival_at': stop.get('arrival_time'), 'departure_at': stop.get('departure_time')}
                     for stop in trip.get('stop_updates', [])]
            times = [stop['arrival_at'] for stop in stops]
            one_second = len(times) >= 3 and all(isinstance(value, (int, float)) for value in times) and all(b - a == 1 for a, b in zip(times, times[1:]))
            target = {stop['stop_id']: stop for stop in stops}
            span = None if not {'A27S', 'A41S'} <= target.keys() else target['A41S']['arrival_at'] - target['A27S']['departure_at']
            timeline.append({'captured_at': snapshot['captured_at'], 'source_updated_at': snapshot.get('source_updated_at'),
                             'snapshot_sha256': snapshot.get('sha256'), 'trip_id': trip['id'],
                             'stop_count': len(stops), 'all_successive_arrivals_one_second_apart': one_second,
                             'origin_to_destination_forecast_span_seconds': span, 'stop_updates': stops})
            post_last_capture = None
        if not found and timeline and post_last_capture is None:
            post_last_capture = {'captured_at': snapshot['captured_at'], 'source_updated_at': snapshot.get('source_updated_at'), 'snapshot_sha256': snapshot.get('sha256')}
assert timeline and target_labels
last = timeline[-1]
assert last['origin_to_destination_forecast_span_seconds'] == 10 and last['all_successive_arrivals_one_second_apart']
for stops in target_labels.values():
    assert stops['A27S']['departure_at'] == 1795010130
    assert stops['A41S']['arrival_at'] == 1795010140
    assert stops['A27S']['stop_last_observed_at'] == stops['A41S']['stop_last_observed_at'] == 1795010159
report = {'schema_version': 'november-feed-replay-source-anomaly-audit-v1', 'status': 'INVALID_OUTCOME_PROXY_CONFIRMED',
          'case_id': CASE, 'canonical_trip_id': 'MTA_EVENT:ace:20261118:C:' + TRIP,
          'route_id': 'google-derived-9fab23eb821baf0cf1b650a3', 'from_stop_id': 'A27S', 'to_stop_id': 'A41S',
          'finding': 'A full downstream stop sequence repeatedly advances in one-second increments. Final journal endpoints therefore imply an impossible 10-second ride across ten stop intervals. Joint later disappearance passes individual endpoint freshness and confirmation checks but does not establish actual movement.',
          'required_interpretation': 'Do not count this selected route outcome as a verified saving. Apply any resulting endpoint/segment quality exclusion equally to Stay and Switch and to every compared policy, without using outcome quality to choose another train.',
          'source_files': source_specs,
          'source_manifest': {'path': str(manifest_path.relative_to(ROOT)), 'sha256': sha(manifest_path)},
          'audit_script_sha256': sha(Path(__file__)),
          'timeline_capture_count': len(timeline),
          'one_second_sequence_capture_count': sum(row['all_successive_arrivals_one_second_apart'] for row in timeline),
          'origin_destination_ten_second_capture_count': sum(row['origin_to_destination_forecast_span_seconds'] == 10 for row in timeline),
          'first_capture': timeline[0]['captured_at'], 'last_capture': timeline[-1]['captured_at'],
          'first_full_capture_after_last_presence': post_last_capture,
          'final_daily_labels': target_labels, 'source_timeline': timeline,
          'limitations': ['This audit examines original normalized feed snapshots and journal-derived labels bound to their acquisition manifest, not an independent passenger observation.', 'No physical cause or exact train movement is inferred from the malformed prediction sequence.']}
path = ROOT / 'algo/reports/november-feed-replay-source-anomaly-audit.json'
path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({key: report[key] for key in ('status', 'timeline_capture_count', 'one_second_sequence_capture_count', 'origin_destination_ten_second_capture_count', 'first_capture', 'last_capture')}))
print('Artifact SHA', sha(path))
