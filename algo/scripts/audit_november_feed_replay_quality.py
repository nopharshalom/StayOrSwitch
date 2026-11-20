#!/usr/bin/env python3
"""Independently compare geometry, choices and advice before/after quality screening.

Uses only Python's standard library; does not import the evaluator, executor,
archive adapter or outcome-quality producer. The final report hash is required
so partially produced corrected outputs cannot be mistaken for a final run.
"""
from pathlib import Path
from collections import Counter
import argparse
import gzip
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / 'algo/local/november-feed-replay/superseded/initial-v3'
REPORT_REL = 'algo/reports/november-feed-replay-test.json'
OUTPUT = ROOT / 'algo/reports/november-feed-replay-quality-audit.json'
CHECKS = Counter()


def check(condition, name):
    assert condition, name
    CHECKS[name] += 1


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def trace_without_quality(trace):
    # No candidate, selection, event key, timestamp or other action field removed.
    return [{key: value for key, value in row.items()
             if not (row['action'] == 'BOARD' and key == 'outcome_quality')}
            for row in trace]


def leg_identity(leg):
    return (leg['canonical_trip_id'], leg['from_stop_id'], leg['to_stop_id'], leg['departure_at'], leg['arrival_at'])


def distance_km(origin, destination, coordinates, radius):
    """Independent spherical vector-angle calculation (not producer haversine)."""
    vectors = []
    for stop in (origin, destination):
        row = coordinates[stop]
        latitude = math.radians(row['latitude'])
        longitude = math.radians(row['longitude'])
        vectors.append((math.cos(latitude) * math.cos(longitude), math.cos(latitude) * math.sin(longitude), math.sin(latitude)))
    a, b = vectors
    cross = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    return radius * math.atan2(math.sqrt(sum(value * value for value in cross)), sum(x * y for x, y in zip(a, b)))


def leg_metrics(leg, coordinates, radius):
    check(leg['from_stop_id'] in coordinates and leg['to_stop_id'] in coordinates, 'leg_coordinate_coverage')
    distance = distance_km(leg['from_stop_id'], leg['to_stop_id'], coordinates, radius)
    duration = leg['arrival_at'] - leg['departure_at']
    check(duration > 0, 'completed_leg_has_positive_duration')
    return distance, duration, distance * 3600 / duration


def summary(outcome):
    return {key: outcome.get(key) for key in ('status', 'reason', 'leg_index', 'platform_ready_at', 'total_duration_seconds',
            'destination_arrival_at', 'components', 'conditional_on_unverified_selected_wait', 'trace_counters')}


def advice_projection(report):
    result = {}
    for case in report['cases']:
        modes = {}
        for mode, content in case['modes'].items():
            modes[mode] = {'strict_decision': content['strict_decision'],
                           'selected_routes': [{key: value for key, value in route.items() if key != 'route_execution_outcome'}
                                               for route in content['selected_routes']]}
        result[case['id']] = {'decision_at': case['decision_at'], 'reference_route_id': case['reference_route_id'],
                              'primary': case['primary'], 'modes': modes}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--final-report-sha256', required=True)
    args = parser.parse_args()
    final_report_path = ROOT / REPORT_REL
    check(sha(final_report_path) == args.final_report_sha256, 'final_report_completion_hash')
    preservation = json.loads((OLD / 'preservation-manifest.json').read_text())
    preserved_hashes = {row['path']: row['sha256'] for row in preservation['files']}
    check(sha(OLD / REPORT_REL) == preserved_hashes[REPORT_REL], 'preserved_initial_report_hash')
    initial_report = json.loads((OLD / REPORT_REL).read_text())
    final_report = json.loads(final_report_path.read_text())
    config_path = ROOT / 'data/config/november-feed-outcome-quality.json'
    config = json.loads(config_path.read_text())
    station_path = ROOT / config['station_source']['path']
    check(sha(station_path) == config['station_source']['sha256'], 'station_subset_config_hash')
    stations = json.loads(station_path.read_text())
    coordinates = stations['coordinates']
    raw_station_path = ROOT / stations['raw_official_source']['path']
    check(sha(raw_station_path) == stations['raw_official_source']['sha256'], 'archived_official_coordinate_source_hash')
    official = {row['gtfs_stop_id']: row for row in json.loads(raw_station_path.read_text())}
    for stop_id, row in coordinates.items():
        source = official[row['station_stop_id']]
        check(stop_id == row['station_stop_id'] + 'S', 'platform_station_identity')
        check(float(source['gtfs_latitude']) == row['latitude'] and float(source['gtfs_longitude']) == row['longitude'], 'coordinates_equal_archived_official_values')
    check(config['max_straight_line_speed_kmh'] == 300 and config['scope'] == 'POST_SELECTION_SELECTED_TRAIN_OUTCOME_ONLY', 'declared_post_selection_quality_ceiling')
    check(config['changes_forecasts_or_candidate_selection'] is False and config['applies_to_all_routes_modes_and_comparison_signs'] is True, 'declared_symmetric_outcome_only_scope')
    radius = config['earth_radius_km']
    ceiling = config['max_straight_line_speed_kmh']
    initial_advice = advice_projection(initial_report)
    final_advice = advice_projection(final_report)
    check(initial_advice.keys() == final_advice.keys(), 'same_case_cohort')
    for case_id in initial_advice:
        check(initial_advice[case_id] == final_advice[case_id], 'all_mode_advice_predictions_and_forecast_trains_unchanged')
    check(initial_report['corridors'] == final_report['corridors'], 'route_templates_and_walking_unchanged')
    initial_shared_rel = initial_report['shared_route_execution']['path']
    initial_shared_path = OLD / initial_shared_rel
    check(sha(initial_shared_path) == initial_report['shared_route_execution']['sha256'] == preserved_hashes[initial_shared_rel], 'preserved_initial_shared_hash')
    initial_shared = json.load(gzip.open(initial_shared_path, 'rt'))
    initial_routes = {}
    initial_unique = set()
    initial_inferred_unique = set()
    initial_queries = 0
    initial_inferred_queries = 0
    speed_bands = Counter({str(speed): 0 for speed in (100, 160, 200, 300)})
    inferred_speed_bands = Counter({str(speed): 0 for speed in (100, 160, 200, 300)})
    affected = []
    initial_max = 0
    for case in initial_shared['cases']:
        for route_id, outcome in case['outcomes'].items():
            key = (case['case_id'], route_id)
            legs = outcome.get('selected_legs', outcome.get('completed_legs', []))
            bad_legs = []
            for leg in legs:
                initial_queries += 1
                initial_inferred_queries += outcome['status'] == 'INFERRED'
                initial_unique.add(leg_identity(leg))
                if outcome['status'] == 'INFERRED':
                    initial_inferred_unique.add(leg_identity(leg))
                distance, duration, speed = leg_metrics(leg, coordinates, radius)
                initial_max = max(initial_max, speed)
                for threshold in (100, 160, 200, 300):
                    speed_bands[str(threshold)] += speed > threshold
                    if outcome['status'] == 'INFERRED':
                        inferred_speed_bands[str(threshold)] += speed > threshold
                if speed > ceiling:
                    bad_legs.append(leg)
                    affected.append({'case_id': case['case_id'], 'route_id': route_id, 'initial_status': outcome['status'],
                                     'canonical_trip_id': leg['canonical_trip_id'], 'leg_index': leg['leg_index'],
                                     'from_stop_id': leg['from_stop_id'], 'to_stop_id': leg['to_stop_id'],
                                     'departure_at': leg['departure_at'], 'arrival_at': leg['arrival_at'],
                                     'duration_seconds': duration, 'straight_line_km': distance, 'implied_speed_kmh': speed})
            trace = trace_without_quality(outcome['update_trace'])
            if bad_legs:
                bad = bad_legs[0]
                board_index = next(index for index, row in enumerate(trace) if row['action'] == 'BOARD'
                                   and row['leg_index'] == bad['leg_index'] and row['event_key'] == bad['event_key'])
                initial_routes[key] = {'summary': summary(outcome), 'legs': legs, 'bad_leg': bad,
                                       'trace_prefix': trace[:board_index + 1]}
            else:
                initial_routes[key] = {'summary': summary(outcome), 'leg_ids': [leg_identity(leg) for leg in legs],
                                       'trace_hash': json_sha(trace)}
    del initial_shared
    check(initial_inferred_queries == 11693 and len(initial_inferred_unique) == 5491, 'initial_inferred_leg_inventory_matches_initial_scan')
    check(initial_queries == 12640 and len(initial_unique) == 5639, 'all_initial_completed_leg_inventory')
    inferred_affected = [row for row in affected if row['initial_status'] == 'INFERRED']
    check(len(inferred_affected) == 10 and len({(row['canonical_trip_id'], row['from_stop_id'], row['to_stop_id']) for row in inferred_affected}) == 4, 'four_unique_implausible_inferred_legs_ten_route_occurrences')
    check(len(affected) == 11 and len({(row['canonical_trip_id'], row['from_stop_id'], row['to_stop_id']) for row in affected}) == 5, 'additional_implausible_completed_leg_on_already_unknown_route')
    check(all(count == 10 for count in inferred_speed_bands.values()), 'same_inferred_exclusions_at_100_160_200_300_ceiling_sensitivity')
    final_shared_path = ROOT / final_report['shared_route_execution']['path']
    check(sha(final_shared_path) == final_report['shared_route_execution']['sha256'], 'corrected_shared_report_hash')
    final_shared = json.load(gzip.open(final_shared_path, 'rt'))
    final_queries = final_inferred_queries = 0
    final_unique = set()
    final_max = 0
    affected_routes = []
    seen_keys = set()
    for case in final_shared['cases']:
        for route_id, outcome in case['outcomes'].items():
            key = (case['case_id'], route_id)
            seen_keys.add(key)
            old = initial_routes[key]
            legs = outcome.get('selected_legs', outcome.get('completed_legs', []))
            for leg in legs:
                final_queries += 1
                final_inferred_queries += outcome['status'] == 'INFERRED'
                final_unique.add(leg_identity(leg))
                distance, duration, speed = leg_metrics(leg, coordinates, radius)
                final_max = max(final_max, speed)
                check(speed <= ceiling, 'all_final_completed_and_inferred_legs_pass_independent_geometry')
                quality = leg['outcome_quality']
                check(quality['status'] == 'PASSED' and quality['flags'] == [] and quality['selection_affected'] is False, 'completed_leg_quality_flag_matches_geometry')
                check(math.isclose(quality['distance_km'], distance, abs_tol=1e-8) and math.isclose(quality['implied_speed_kmh'], speed, abs_tol=1e-7), 'independent_vector_geometry_matches_recorded_quality')
                check(quality['raw_departure_at'] == leg['departure_at'] and quality['raw_arrival_at'] == leg['arrival_at'], 'raw_endpoint_values_preserved')
            trace = trace_without_quality(outcome['update_trace'])
            if 'bad_leg' not in old:
                check(json_sha(trace) == old['trace_hash'], 'unaffected_route_trace_identical_except_board_quality')
                check(summary(outcome) == old['summary'], 'unaffected_route_outcome_unchanged')
                check([leg_identity(leg) for leg in legs] == old['leg_ids'], 'unaffected_selected_train_endpoints_unchanged')
                continue
            bad = old['bad_leg']
            check(outcome['status'] == 'UNAVAILABLE' and outcome['reason'] == 'SELECTED_OUTCOME_IMPLAUSIBLE_TRAVEL_TIME', 'implausible_route_becomes_unknown')
            check(trace == old['trace_prefix'] and trace[-1]['action'] == 'BOARD', 'same_choice_and_boarding_trace_prefix_no_alternative_fallback')
            check(trace[-1]['event_key'] == bad['event_key'] and trace[-1]['at'] == bad['departure_at'], 'same_bad_train_boarding_preserved')
            event = outcome['event']
            check(event['canonical_trip_id'] == bad['canonical_trip_id'] and event['departure_at'] == bad['departure_at'] and event['arrival_at'] == bad['arrival_at'], 'rejected_raw_endpoint_values_preserved')
            check('IMPLAUSIBLE_LEG_TRAVEL_TIME' in event['endpoint_flags']['alighting'] and not event['endpoint_flags']['boarding'], 'only_arrival_outcome_invalidated_not_boarding')
            quality = outcome['outcome_quality']
            distance, duration, speed = leg_metrics(bad, coordinates, radius)
            check(quality['status'] == 'REJECTED_IMPLAUSIBLE_TRAVEL_TIME' and quality['selection_affected'] is False and speed > ceiling, 'rejected_quality_status_matches_geometry')
            check(math.isclose(quality['distance_km'], distance, abs_tol=1e-8) and math.isclose(quality['implied_speed_kmh'], speed, abs_tol=1e-7), 'rejected_independent_geometry_matches_record')
            check([leg_identity(leg) for leg in legs] == [leg_identity(leg) for leg in old['legs'] if leg['leg_index'] < bad['leg_index']], 'no_later_transfer_execution_after_invalid_selected_arrival')
            affected_routes.append({'case_id': case['case_id'], 'route_id': route_id, 'initial_status': old['summary']['status'],
                                    'final_status': outcome['status'], 'final_reason': outcome['reason'], 'unchanged_trace_prefix_actions': len(trace),
                                    'selected_bad_train': bad['canonical_trip_id'], 'leg_index': bad['leg_index'], 'implied_speed_kmh': speed})
    check(seen_keys == initial_routes.keys(), 'same_route_execution_query_set')
    check(len(affected_routes) == 11, 'all_eleven_affected_route_occurrences_stop_at_invalid_leg')
    manifest_path = ROOT / final_report['archive']['manifest']['path']
    check(sha(manifest_path) == final_report['archive']['manifest']['sha256'], 'final_archive_manifest_binding')
    producer_paths = ['data/route_outcome_sanity.py', 'data/feed_route_archive.py', 'algo/stayorswitch/feed_execution.py', 'algo/scripts/evaluate_november_feed_replay.py']
    sources = {name: {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)} for name, path in
               [('initial_report', OLD / REPORT_REL), ('final_report', final_report_path), ('initial_shared', initial_shared_path),
                ('final_shared', final_shared_path), ('quality_config', config_path), ('station_coordinates', station_path),
                ('official_station_archive', raw_station_path), ('final_archive_manifest', manifest_path),
                ('preservation_manifest', OLD / 'preservation-manifest.json'), ('audit_script', Path(__file__))]}
    result = {'schema_version': 'november-feed-replay-quality-independent-audit-v1', 'status': 'PASS',
              'scope': 'All initial and corrected route queries, all completed/inferred legs, all compact report advice; no raw trip archive re-ingestion.',
              'checks': dict(sorted(CHECKS.items())), 'total_checks': sum(CHECKS.values()),
              'sources': sources, 'producer_hashes': {path: sha(ROOT / path) for path in producer_paths},
              'initial': {'route_queries': len(initial_routes), 'completed_leg_queries': initial_queries, 'inferred_route_leg_queries': initial_inferred_queries,
                          'unique_completed_legs': len(initial_unique), 'unique_inferred_route_legs': len(initial_inferred_unique), 'maximum_implied_speed_kmh': initial_max, 'completed_leg_threshold_exceedance_occurrences': dict(speed_bands), 'inferred_route_threshold_exceedance_occurrences': dict(inferred_speed_bands)},
              'corrected': {'route_queries': len(seen_keys), 'completed_leg_queries': final_queries, 'inferred_route_leg_queries': final_inferred_queries,
                            'unique_completed_legs': len(final_unique), 'maximum_implied_speed_kmh': final_max,
                            'affected_route_queries': len(affected_routes), 'affected_unique_events': 5, 'previously_inferred_route_queries_now_unknown': 10, 'previously_unknown_routes_stopping_earlier': 1},
              'affected_initial_leg_occurrences': affected, 'affected_route_outcomes': affected_routes,
              'unchanged_advice_case_count': len(initial_advice),
              'limitations': ['The 300 km/h ceiling is a deliberately permissive design quality rule, not a measured subway operating-speed limit.',
                              'Passing this screen does not prove final MTA predictions equal actual passenger movement.',
                              'Initial November outcomes had already been examined; this is a post-hoc quality repair, not a new held-out evaluation.',
                              'Straight-line station distance is a lower bound on travel distance; track geometry and intermediate dwell times are not modeled.']}
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('PASS', result['total_checks'], 'checks;', sha(OUTPUT), flush=True)
    print(json.dumps({'initial': result['initial'], 'corrected': result['corrected']}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
