#!/usr/bin/env python3
"""Bounded, independent source-cache checks for six frozen feed replay routes."""
from pathlib import Path
from collections import Counter, defaultdict
from bisect import bisect_right
import datetime
import gzip
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'algo/reports/november-feed-replay-test.json'
OUTPUT = ROOT / 'algo/reports/november-feed-replay-case-audit.json'
EXPECTED_REPORT_SHA = '5332da553a917b75697b93967362bbf0f8b595de00a8a3091457a269acb9379b'
CHECKS = Counter()


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def check(condition, name):
    assert condition, name
    CHECKS[name] += 1


def epoch(value):
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    return None


def stream_events(path, metadata):
    """Stream one immutable cache; retain trailing full-capture records."""
    decoder = json.JSONDecoder()
    buffer = ''
    marker = '"events":['
    with gzip.open(path, 'rt') as handle:
        while marker not in buffer:
            chunk = handle.read(65536)
            assert chunk, 'Missing events array'
            buffer += chunk
        buffer = buffer.split(marker, 1)[1]
        while True:
            buffer = buffer.lstrip(' \r\n,')
            if buffer.startswith(']'):
                tail = (buffer[1:] + handle.read()).lstrip(' \r\n,')
                metadata.update(json.loads('{' + tail))
                return
            try:
                event, length = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                chunk = handle.read(65536)
                assert chunk, 'Incomplete source event'
                buffer += chunk
                continue
            yield event
            buffer = buffer[length:]


def key_for(event):
    return (event['feed_id'], event['route_id'], event['from_stop_id'], event['to_stop_id'])


def leg_keys(leg):
    return [(leg['feed_id'], line, leg['from_stop_id'], leg['to_stop_id'])
            for line in leg.get('route_ids', [leg['route_id']])]


report = json.loads(REPORT.read_text())
check(sha(REPORT) == EXPECTED_REPORT_SHA, 'frozen_report_hash')
shared_path = ROOT / report['shared_route_execution']['path']
check(sha(shared_path) == report['shared_route_execution']['sha256'], 'shared_outcome_hash')
source_path = ROOT / report['archive']['source_archive']['path']
check(sha(source_path) == report['archive']['source_archive']['sha256'], 'immutable_source_cache_hash')
shared = json.load(gzip.open(shared_path, 'rt'))
outcomes = {case['case_id']: case['outcomes'] for case in shared['cases']}
cases = {case['id']: case for case in report['cases']}
templates = {route['id']: route for corridor in report['corridors'] for route in corridor['routes']}
specs = [
    ('recovered_comparable_gain', 'grandcentral_boroughhall--lmm-alert-274536--1793621353693', 'google-route-fae079d4a0a7051e64aa1cda'),
    ('loss_route_execution', 'pilot_hayden_tandon--lmm-alert-274525--1793615892737', 'google-route-88aa6b135b2fe15e2cd08a95'),
    ('due_now_known_miss_then_recovery', 'grandcentral_boroughhall--lmm-alert-274536--1793621053693', 'google-route-54502e7253ac53a2be3cd264'),
    ('selected_departure_unknown', 'courtsquare_timessquare--lmm-alert-274534--1793622093585', 'google-route-9a6888e689fb501e230ccda5'),
    ('conditional_feed_reordering', 'courtsquare_timessquare--lmm-alert-274981--1793880473586', 'google-route-9a6888e689fb501e230ccda5'),
]
examples = []
target_captures = defaultdict(set)
selection_actions = {'SELECT', 'KEEP', 'RESELECT', 'NO_CANDIDATE'}
for purpose, case_id, route_id in specs:
    case = cases[case_id]
    ids = [case['reference_route_id'], route_id] if purpose == 'recovered_comparable_gain' else [route_id]
    example = {'purpose': purpose, 'case_id': case_id, 'corridor_id': case['corridor_id'],
               'local_time': case['local_time'], 'classification': case['modes']['incident_profile']['scores']['classification'],
               'routes': []}
    for rid in ids:
        outcome = outcomes[case_id][rid]
        template = templates[rid]
        example['routes'].append({'route_id': rid, 'route_name': template['name'], 'outcome': outcome})
        for trace in outcome['update_trace']:
            if trace['action'] in selection_actions:
                for key in leg_keys(template['legs'][trace['leg_index']]):
                    target_captures[key].add(trace['snapshot_at'])
    examples.append(example)
del shared, outcomes
metadata = {}
events = {}
source_members = defaultdict(list)
scanned = 0
for event in stream_events(source_path, metadata):
    scanned += 1
    key = key_for(event)
    wanted = target_captures.get(key)
    if not wanted:
        continue
    matched = [row for row in event['observations'] if row['at'] in wanted]
    if not matched:
        continue
    events[(key, event['canonical_trip_id'])] = event
    for observation in matched:
        source_members[(key, observation['at'])].append((event, observation))
print('Source cache scanned; retained', len(events), 'events for', sum(map(len, target_captures.values())), 'target captures.', flush=True)
feed_times = {feed: [row['at'] for row in records] for feed, records in metadata['feed_records'].items()}
endpoint_reviewed = set()


def event_of(leg, event_key):
    found = [events[(key, event_key)] for key in leg_keys(leg) if (key, event_key) in events]
    check(len(found) == 1, 'unique_source_event_identity')
    return found[0]


def endpoint_proof(event):
    identity = (key_for(event), event['canonical_trip_id'])
    if identity in endpoint_reviewed:
        return
    endpoint_reviewed.add(identity)
    for endpoint, side, stop in [('departure', 'boarding', event['from_stop_id']), ('arrival', 'alighting', event['to_stop_id'])]:
        value = event[endpoint + '_at']
        evidence = event['endpoint_evidence'][side]
        if value is None:
            check(bool(event['endpoint_flags'][side]), 'missing_endpoint_has_exclusion_reasons')
            continue
        check(not event['endpoint_flags'][side] and bool(evidence), 'usable_endpoint_has_unflagged_source_evidence')
        for label in evidence:
            check(label['canonical_event_trip_id'] == event['canonical_trip_id'] and label['stop_id'] == stop, 'endpoint_evidence_identity')
            check(epoch(label[endpoint + '_at']) == value, 'endpoint_evidence_time')
            check(label['confirmation_status'] == 'CONFIRMED' and epoch(label['confirmed_at']) is not None, 'endpoint_passage_confirmation')
            check(abs(epoch(label['stop_last_observed_at']) - value) <= 180, 'endpoint_near_event_observation')


for example in examples:
    case = cases[example['case_id']]
    for item in example['routes']:
        outcome = item['outcome']
        template = templates[item['route_id']]
        trace_reviews = []
        prior_choice = {}
        for index, trace in enumerate(outcome['update_trace']):
            leg_index = trace['leg_index']
            leg = template['legs'][leg_index]
            action = trace['action']
            if action in selection_actions:
                at = trace['at']
                captures = feed_times[leg['feed_id']]
                pos = bisect_right(captures, at) - 1
                frame = metadata['feed_records'][leg['feed_id']][pos]
                check(frame['at'] == trace['snapshot_at'], 'selection_uses_latest_full_capture')
                check(frame['eligible'] and frame['source_at'] <= frame['at'] <= at and at - frame['source_at'] <= 120, 'selection_frame_freshness')
                check(frame['sha256'] == trace['snapshot_sha256'] and frame['source_at'] == trace['source_at'], 'selection_frame_source_binding')
                rows = [pair for key in leg_keys(leg) for pair in source_members[(key, frame['at'])]]
                multiplicities = Counter(event['canonical_trip_id'] for event, row in rows)
                pool = []
                for event, row in rows:
                    departure = row.get('departure_forecast_at')
                    if (multiplicities[event['canonical_trip_id']] != 1 or row.get('path_status') != 'COMPATIBLE'
                            or row.get('reason_codes') or row.get('source_at') is None
                            or not row['source_at'] <= row['at'] <= at or at - row['source_at'] > 120
                            or not isinstance(departure, (int, float)) or not math.isfinite(departure)):
                        continue
                    pool.append({'event_key': event['canonical_trip_id'], 'canonical_trip_id': event['canonical_trip_id'],
                                 'departure_forecast_at': departure, 'effective_departure_at': max(at, departure), 'due_now': departure < at})
                pool.sort(key=lambda row: (row['effective_departure_at'], row['canonical_trip_id'], row['event_key']))
                check(pool == trace['candidate_departures'], 'complete_contemporaneous_candidate_pool_and_raw_eta')
                check(bool(pool) and pool[0]['event_key'] == trace['event_key'], 'raw_eta_first_selection_without_endpoint_ranking')
                check(trace['departure_forecast_at'] == pool[0]['departure_forecast_at'], 'selected_raw_eta')
                chosen = event_of(leg, trace['event_key'])
                endpoint_proof(chosen)
                check(trace['selection_reads_endpoint_labels'] is False, 'recorded_selection_label_separation')
                prior_choice[leg_index] = trace
                bad_unselected = sum(event['canonical_trip_id'] != trace['event_key'] and (event['departure_at'] is None or event['arrival_at'] is None) for event, row in rows)
                trace_reviews.append({'action': action, 'at': at, 'snapshot_at': frame['at'], 'snapshot_sha256': frame['sha256'],
                                      'chosen_event_key': trace['event_key'], 'raw_departure_forecast_at': trace['departure_forecast_at'],
                                      'due_now': pool[0]['due_now'], 'source_candidate_count': len(rows), 'eligible_candidate_count': len(pool),
                                      'visible_unselected_with_unusable_endpoints': bad_unselected})
            elif action == 'BOARD':
                previous = prior_choice[leg_index]
                event = event_of(leg, trace['event_key'])
                captures = feed_times[leg['feed_id']]
                next_pos = bisect_right(captures, previous['snapshot_at'])
                check(event['departure_at'] == trace['at'] >= previous['at'], 'boarding_matches_selected_endpoint_without_backdating')
                check(trace['at'] <= captures[next_pos] and trace['at'] - previous['source_at'] <= 120, 'board_before_next_feed_or_expiry')
                check(not any(row['leg_index'] == leg_index and row['action'] in selection_actions for row in outcome['update_trace'][index + 1:]), 'no_reselection_after_boarding')
            elif action == 'MISSED_SELECTED_SERVICE':
                event = event_of(leg, trace['event_key'])
                check(event['departure_at'] == trace['departure_at'] < trace['at'], 'known_miss_is_past_departure')
                next_choice = next(row for row in outcome['update_trace'][index + 1:] if row['action'] in selection_actions)
                previous = prior_choice[leg_index]
                next_capture = feed_times[leg['feed_id']][bisect_right(feed_times[leg['feed_id']], previous['snapshot_at'])]
                check(next_choice['at'] == next_capture > trace['at'], 'miss_waits_for_next_visible_feed')
            elif action == 'UNVERIFIED_BOARDING_BOUNDARY':
                event = event_of(leg, trace['event_key'])
                previous = prior_choice[leg_index]
                check(event['departure_at'] is None and trace['at'] == max(previous['at'], previous['departure_forecast_at']), 'selected_unknown_stops_at_forecast_boundary')
                check(index == len(outcome['update_trace']) - 1 and outcome['reason'] == 'SELECTED_TRAIN_DEPARTURE_UNAVAILABLE', 'unknown_selected_train_has_no_convenient_fallback')
            elif action == 'CONDITIONAL_WAIT':
                event = event_of(leg, trace['event_key'])
                check(event['departure_at'] is None and trace['start_at'] < trace['end_at'] < trace['forecast_departure_at'], 'conditional_wait_ends_before_unknown_boarding_deadline')
                check(outcome['conditional_on_unverified_selected_wait'] is True, 'conditional_wait_disclosed')
        ready = case['decision_at'] + template['access_walk_seconds']
        wait = ride = 0
        for selected in outcome.get('selected_legs', outcome.get('completed_legs', [])):
            leg = template['legs'][selected['leg_index']]
            event = event_of(leg, selected['event_key'])
            endpoint_proof(event)
            check(selected['departure_at'] == event['departure_at'] and selected['arrival_at'] == event['arrival_at'], 'selected_leg_source_endpoint_equality')
            check(selected['platform_ready_at'] == ready <= selected['departure_at'] <= selected['arrival_at'], 'actual_platform_readiness_without_repeated_margin')
            wait += selected['departure_at'] - ready
            ride += selected['arrival_at'] - selected['departure_at']
            ready = selected['arrival_at'] + (template['transfer_walk_seconds'][selected['leg_index']] if selected['leg_index'] < len(template['transfer_walk_seconds']) else template['egress_walk_seconds'])
        if outcome['status'] == 'INFERRED':
            walk = template['access_walk_seconds'] + sum(template['transfer_walk_seconds']) + template['egress_walk_seconds']
            check(abs(ready - outcome['destination_arrival_at']) < 1e-6, 'destination_arrival_arithmetic')
            check(abs(walk + wait + ride - outcome['total_duration_seconds']) < 1e-6, 'full_journey_duration_arithmetic')
        item['source_trace_checks'] = trace_reviews
        item['selected_endpoint_evidence'] = [{key: event[key] for key in ('canonical_trip_id', 'departure_at', 'arrival_at', 'endpoint_flags', 'endpoint_evidence')}
                                              for event in (event_of(template['legs'][j], tr['event_key']) for j, tr in sorted(prior_choice.items()))]
        item['execution_summary'] = {key: outcome.get(key) for key in ('status', 'reason', 'total_duration_seconds', 'conditional_on_unverified_selected_wait', 'trace_counters')}
        item['execution_trace'] = [{key: value for key, value in trace.items() if key not in ('candidate_departures', 'rejected_inputs')} for trace in outcome['update_trace']]
        del item['outcome']

gain = examples[0]
old_report = json.loads((ROOT / 'algo/reports/november-repair-test.json').read_text())
old_case = next(case for case in old_report['cases'] if case['id'] == gain['case_id'])
check(old_case['modes']['incident_profile']['scores']['classification'] == 'UNKNOWN', 'gain_recovered_from_strict_unknown')
savings = gain['routes'][0]['execution_summary']['total_duration_seconds'] - gain['routes'][1]['execution_summary']['total_duration_seconds']
check(savings == cases[gain['case_id']]['modes']['incident_profile']['scores']['inferred_switch_savings_seconds'] == 333.0, 'recovered_pair_savings_arithmetic')
gain['independently_verified_savings_seconds'] = savings
result = {'schema_version': 'november-feed-replay-case-audit-v1', 'status': 'PASS',
          'selection': 'Five purpose-selected post-scoring cases, six route executions. Not an additional performance sample.',
          'case_count': len(examples), 'route_count': sum(len(example['routes']) for example in examples),
          'checks': dict(sorted(CHECKS.items())), 'total_checks': sum(CHECKS.values()),
          'source_events_scanned': scanned, 'source_events_retained': len(events), 'selected_events_with_endpoint_evidence_checked': len(endpoint_reviewed),
          'sources': {'report': {'path': str(REPORT.relative_to(ROOT)), 'sha256': sha(REPORT)},
                      'shared_route_execution': {'path': str(shared_path.relative_to(ROOT)), 'sha256': sha(shared_path)},
                      'immutable_source_cache': {'path': str(source_path.relative_to(ROOT)), 'sha256': sha(source_path)},
                      'audit_script': {'path': str(Path(__file__).relative_to(ROOT)), 'sha256': sha(Path(__file__))}},
          'producer_hashes': {path: sha(ROOT / path) for path in ('data/route_outcome_sanity.py', 'data/feed_route_archive.py', 'algo/stayorswitch/feed_execution.py', 'algo/scripts/evaluate_november_feed_replay.py')},
          'quality_config_sha256': sha(ROOT / 'data/config/november-feed-outcome-quality.json'),
          'examples': examples,
          'limitations': ['Final MTA endpoint records are screened proxies, not independent passenger measurements.',
                          'The conditional example assumes waiting until a later visible feed before the unknown train forecast boundary; it does not prove that the first train had not physically departed.',
                          'The loss example audits its selected route execution; its alternative route is outside this six-route source review.',
                          'This checks the hash-bound immutable cache and its embedded endpoint evidence. It does not re-ingest raw GTFS-RT archives or rescan daily label files.',
                          'Purpose-selected examples demonstrate local consistency, not general performance or a fresh test set.']}
OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print('PASS', result['total_checks'], 'checks;', sha(OUTPUT), flush=True)
