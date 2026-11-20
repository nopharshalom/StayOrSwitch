#!/usr/bin/env python3
"""Independent full-October eligibility and aggregate verification."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'algo')]
from data.delay_profiles.incidents import IncidentIndex
from data.october.sources import read_snapshots
from data.delay_profiles.estimator import ProfileEstimator

checks = 0
def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(message)

def load(path):
    path = Path(path)
    with (gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()) as stream:
        return json.load(stream)

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()

def dates(first, last):
    day = datetime.fromisoformat(first).date()
    end = datetime.fromisoformat(last).date()
    while day <= end:
        yield day.isoformat()
        day += timedelta(days=1)

def main():
    artifact = ROOT / 'data/artifacts/october-2026-profiles-full-train.json.gz'
    profile = load(artifact)
    manifest = load(ROOT / 'data/artifacts/october-2026-profiles-full-train.manifest.json')
    frozen = load(ROOT / 'data/manifests/full-october-fit-frozen.json')
    report = load(ROOT / 'data/reports/full-october-fit.json')
    preserved = load(ROOT / 'data/manifests/november-preservation.json')
    ProfileEstimator(artifact)
    check(sha(artifact) == manifest['sha256'] == frozen['artifact']['sha256'], 'artifact hash')
    check(profile['fit_split'] == 'train', 'predictive training role')
    check(profile['configuration']['splits'] == {'train': ['2026-10-01', '2026-10-31']}, 'training date split')
    check(profile['november_outcomes_used_for_fit'] is False, 'outcome exclusion declaration')
    check(profile['configuration']['full_month_fit']['boundary_input_dates'] == ['2026-11-01', '2026-11-18'], 'updated formal window')
    check(all('2026-11-19.' not in p for p in frozen['source_sha256'] if 'november-2026' in p), 'Nov19 excluded from fit input membership')
    check(profile['seal'] == manifest['profile_seal'] == frozen['profile_seal'] == report['profile_seal'], 'seal parity')
    check(all(not ('november-2026' in p and ('labels' in p or 'snapshots' in p)) for p in frozen['source_sha256']), 'November only inventories/source metadata')
    for name, expected in preserved['files'].items():
        check(sha(ROOT / name) == expected, 'old artifact changed: ' + name)
    for name, expected in frozen['code_sha256'].items():
        check(sha(ROOT / name) == expected, 'fit code changed: ' + name)
    for name, expected in frozen['source_sha256'].items():
        check(sha(ROOT / name) == expected, 'fit input changed: ' + name)
    input_manifest_path = ROOT / 'data/manifests/november-2026-inputs.json'
    input_manifest = load(input_manifest_path)
    check(input_manifest['stage'] == 'INPUTS_PREPARED', 'normalized input freeze status')
    input_days = {row['date']: row for row in input_manifest['days']}
    for day in dates('2026-11-01', '2026-11-18'):
        for kind in ('trips', 'alerts'):
            item = input_days[day]['outputs'][kind]
            check(frozen['source_sha256'].get(item['path']) == item['sha256'],
                  'fit source differs from acquisition input freeze: ' + day + ' ' + kind)

    cutoff = datetime(2026, 11, 1, tzinfo=ZoneInfo('America/New_York')).timestamp()
    check(cutoff == datetime.fromisoformat('2026-11-01T04:00:00+00:00').timestamp(), 'DST cutoff')
    november_trips = set()
    for day in dates('2026-11-01', '2026-11-18'):
        values = load(ROOT / 'data/processed/november-2026' / (day + '.trips.json.gz'))
        for trip in values.values():
            parts = [trip.get(k) for k in ('feed_id', 'start_date', 'route_id', 'trip_id')]
            if (all(isinstance(v, str) and v for v in parts)
                    and re.fullmatch(r'\d{8}', parts[1])
                    and re.fullmatch(r'[0-9]{6}_.+', parts[3])):
                november_trips.add('MTA_EVENT:' + ':'.join(quote(v, safe='') for v in parts))

    def alerts():
        for first, last, directory in [('2026-10-01', '2026-10-31', 'october'),
                                        ('2026-11-01', '2026-11-18', 'november-2026')]:
            for day in dates(first, last):
                yield from read_snapshots(ROOT / 'data/processed' / directory / (day + '.alerts.jsonl.gz'))

    index = IncidentIndex(alerts(), max_age_seconds=300)
    unplanned = {v['incident_id'] for v in index.versions.values() if v['state'] in ('DISRUPTION', 'SEVERE')}
    first_seen, final_end, active = {}, {}, set()
    for entry in index.entries:
        if not entry['valid']:
            continue
        current = {index.versions[k]['incident_id'] for k in entry['version_ids']}
        for identifier in active - current:
            final_end[identifier] = entry['captured_at']
        for identifier in current:
            first_seen.setdefault(identifier, entry['captured_at'])
            final_end[identifier] = entry['captured_at']
        active = current
    for identifier in active:
        final_end[identifier] = datetime(2026, 11, 19, tzinfo=ZoneInfo('America/New_York')).timestamp()
    crossing = {identifier for identifier in unplanned
                if first_seen[identifier] < cutoff <= final_end[identifier]}

    groups = profile['groups']
    # Verify broad route means at a fixed forecast band, all severe groups, and
    # deterministic exact groups spread across the serialized group inventory.
    chosen = set()
    exact = []
    for key, group in groups.items():
        identity = json.loads(key)
        if (identity['state'] == 'ANY' and identity['from_stop_id'] == 'ANY'
                and identity['horizon'] == '15_30_MIN'):
            chosen.add(key)
        if identity['state'] == 'SEVERE':
            chosen.add(key)
        if identity['state'] == 'ANY' and identity['from_stop_id'] != 'ANY':
            exact.append(key)
    exact.sort()
    chosen.update(exact[::max(1, len(exact) // 40)])
    lookup = defaultdict(list)
    for key in chosen:
        identity = json.loads(key)
        lookup[(identity['target'], identity['route_id'], identity['horizon'])].append((key, identity))
    members = defaultdict(dict)
    counts, days, eligible_days = Counter(), Counter(), Counter()
    eligible_digest = hashlib.sha256()
    previous = None
    observation_path = ROOT / 'data/processed/october/profile-observations.jsonl.gz'
    for line in gzip.open(observation_path, 'rt'):
        row = json.loads(line)
        counts['representative_observations'] += 1
        days[row['date']] += 1
        order = (row['decision_at'], row['id'])
        check(previous is None or order > previous, 'unique sorted observation sequence')
        previous = order
        check('2026-10-01' <= row['date'] <= '2026-10-31', 'nonOctober observation')
        if not row['usable']:
            counts['unusable_observations'] += 1
            continue
        confirmed = row['label_confirmed_at']
        if confirmed is None:
            counts['OUTCOME_RECEIPT_NOT_CONFIRMED'] += 1
            continue
        if confirmed >= cutoff:
            counts['OUTCOME_CONFIRMED_AFTER_DEVELOPMENT'] += 1
            continue
        if (row.get('canonical_event_trip_id') or row['trip_id']) in november_trips:
            counts['TRAIN_CROSSES_DEVELOPMENT_BOUNDARY'] += 1
            continue
        if set(row['context'].get('incident_ids') or []) & crossing:
            counts['INCIDENT_CROSSES_DEVELOPMENT_BOUNDARY'] += 1
            continue
        counts['eligible_observations'] += 1
        eligible_days[row['date']] += 1
        eligible_digest.update((row['id'] + '\n').encode())
        local = datetime.fromtimestamp(row['decision_at'], ZoneInfo('America/New_York'))
        day_type = 'SATURDAY' if local.weekday() == 5 else 'SUNDAY' if local.weekday() == 6 else 'WEEKDAY'
        period = next(p['id'] for p in profile['configuration']['periods'] if p['start_hour'] <= local.hour < p['end_hour'])
        context = row['context']
        for key, identity in lookup.get((row['target'], row['route_id'], row['horizon_group']), []):
            if any(identity[k] not in ('ANY', value) for k, value in [
                    ('from_stop_id', row['from_stop_id']), ('to_stop_id', row['to_stop_id']),
                    ('day_type', day_type), ('period', period),
                    ('state', context.get('state', 'UNKNOWN')),
                    ('cause', context.get('cause') or 'UNKNOWN'),
                    ('evidence_status', context.get('evidence_status', 'UNKNOWN'))]):
                continue
            direction = row['from_stop_id'][-1] if row['from_stop_id'][-1] in 'NS' else 'UNKNOWN'
            if identity['direction'] != direction:
                continue
            if row['event_id'] not in members[key]:
                incidents = context.get('severe_incident_ids' if identity['state'] == 'SEVERE' else 'incident_ids') or []
                members[key][row['event_id']] = (row['residual_seconds'], row['date'], incidents)

    check(sorted(days) == list(dates('2026-10-01', '2026-10-31')), 'all31dates')
    for key, value in counts.items():
        check(report['counts'].get(key, 0) == value, 'eligibility count mismatch: ' + key)
    check(dict(sorted(days.items())) == report['representative_observations_by_day'], 'daily source counts')
    for key in sorted(chosen):
        expected = groups[key]
        values = list(members[key].values())
        errors = sorted(v[0] for v in values)
        check(len(values) == expected['event_count'], 'group event count ' + key)
        check(len({v[1] for v in values}) == expected['date_count'], 'group date count ' + key)
        check(len({i for v in values for i in v[2]}) == expected['incident_count'], 'group incident count ' + key)
        count = len(values)
        stats = expected['statistics']
        for field, actual in [('mean_signed_seconds', sum(errors) / count),
                              ('mean_positive_seconds', sum(max(x, 0) for x in errors) / count),
                              ('probability_over_5_minutes', sum(x > 300 for x in errors) / count),
                              ('probability_over_10_minutes', sum(x > 600 for x in errors) / count)]:
            check(math.isclose(actual, stats[field], rel_tol=1e-12, abs_tol=1e-10), field + ' ' + key)
        for field, q in [('median_seconds', .5), ('p80_seconds', .8), ('p90_seconds', .9)]:
            position = (count - 1) * q
            low, fraction = int(position), position - int(position)
            actual = errors[low] * (1 - fraction) + errors[min(low + 1, count - 1)] * fraction
            check(math.isclose(actual, stats[field], rel_tol=1e-12, abs_tol=1e-10), field + ' ' + key)

    value = {'schema_version': 'full-october-fit-independent-audit-v1', 'status': 'PASSED',
             'checks': checks, 'profile_sha256': sha(artifact), 'profile_seal': profile['seal'],
             'source_observation_sha256': sha(observation_path),
             'training_cutoff_utc': '2026-11-01T04:00:00Z',
             'training_counts_independently_recomputed': dict(counts),
             'eligible_observations_by_day': dict(sorted(eligible_days.items())),
             'eligible_observation_id_digest': eligible_digest.hexdigest(),
             'november_input_dates': ['2026-11-01', '2026-11-18'],
             'november_acquisition_input_manifest_sha256': sha(input_manifest_path),
             'november_physical_trip_id_count': len(november_trips),
             'crossing_unplanned_family_count': len(crossing),
             'crossing_unplanned_families': sorted(crossing),
             'independently_reconstructed_group_count': len(chosen),
             'independently_reconstructed_group_keys': sorted(chosen),
             'protected_artifact_count': len(preserved['files']),
             'november_outcome_labels_opened': False,
             'limitations': ['Endpoint targets remain screened final MTA prediction proxies.',
                            'All eligibility rows and sampled aggregate means/support/quantiles were checked; not every aggregate was reconstructed.'],
             'audit_script_sha256': sha(Path(__file__))}
    out = ROOT / 'data/manifests/full-october-fit-audit.json'
    out.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: value[k] for k in ['status', 'checks', 'training_counts_independently_recomputed',
          'independently_reconstructed_group_count', 'crossing_unplanned_family_count', 'protected_artifact_count']}))


if __name__ == '__main__':
    main()
