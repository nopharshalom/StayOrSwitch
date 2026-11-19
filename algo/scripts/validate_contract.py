#!/usr/bin/env python3
"""Validate Step 1 schemas, simulated fixtures, and cross-field invariants.

This is an offline contract checker, not an ETA estimator or API server.
"""
import argparse
import copy
import json
import math
import re
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / 'contracts' / 'evaluate.schema.json'
FORMAT = FormatChecker()


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp requires an explicit UTC offset.')
    return parsed


@FORMAT.checks('date-time', raises=(ValueError, TypeError))
def valid_timestamp(value):
    if not isinstance(value, str):
        return True
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)', value):
        return False
    instant(value)
    return True


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    def reject_constant(value):
        raise ValueError('Non-finite JSON number: ' + value)
    document = json.loads(path.read_text(), parse_constant=reject_constant)
    finite_numbers(document)
    return document


def finite_numbers(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'All numeric values must be finite.')
    elif isinstance(value, dict):
        for child in value.values():
            finite_numbers(child)
    elif isinstance(value, list):
        for child in value:
            finite_numbers(child)


def schema_validate(document, definition, schema):
    finite_numbers(document)
    selected = dict(schema, **{'$ref': '#/$defs/' + definition})
    Draft202012Validator(selected, format_checker=FORMAT).validate(document)


def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=0.000001)


def request_invariants(request):
    routes = request['itineraries']
    ids = [route['id'] for route in routes]
    require(len(ids) == len(set(ids)), 'Itinerary identifiers must be unique.')
    current = request['current_itinerary_id']
    require(current is None or current in ids, 'Unknown current_itinerary_id.')
    cutoff = instant(request['decision_time'])
    locations = {}
    for route in routes:
        require(instant(route['provider']['queried_at']) <= cutoff, 'Provider query occurred after decision time.')
        legs = route['legs']
        leg_ids = [leg['id'] for leg in legs]
        require(len(leg_ids) == len(set(leg_ids)), 'Leg identifiers must be unique within an itinerary.')
        require(legs[0]['from'] == request['origin'], 'Itinerary must start at the common origin.')
        require(legs[-1]['to'] == request['destination'], 'Itinerary must end at the common destination.')
        for previous, following in zip(legs, legs[1:]):
            require(previous['to'] == following['from'], 'Disconnected itinerary legs; include transfer walking.')
        for leg in legs:
            for location in [leg['from'], leg['to']]:
                existing = locations.setdefault(location['id'], location)
                require(existing == location, 'A location identifier has conflicting definitions.')
            departure, arrival = leg['provider_departure_at'], leg['provider_arrival_at']
            if departure is not None and arrival is not None:
                require(instant(arrival) >= instant(departure), 'Provider arrival precedes departure.')
        # Provider ETAs may be old; they are not used as decision-time outcome labels.


def response_invariants(request, response):
    for field in ['schema_version', 'request_id', 'data_mode', 'decision_time', 'current_itinerary_id']:
        require(request[field] == response[field], 'Request/response mismatch: ' + field)
    cutoff = instant(request['decision_time'])
    require(instant(response['evaluated_at']) >= cutoff, 'evaluated_at precedes decision time.')
    inputs = {route['id']: route for route in request['itineraries']}
    results = response['itineraries']
    ids = [route['id'] for route in results]
    require(len(ids) == len(set(ids)) and set(ids) == set(inputs), 'Exactly one result per supplied itinerary is required.')
    for state in response['data_status'].values():
        if state['status'] != 'MISSING':
            require(instant(state['source_updated_at']) <= instant(state['fetched_at']) <= cutoff,
                    'Feed observations must be available by decision_time.')
    uses_model = False
    for result in results:
        if result['status'] != 'ESTIMATED':
            continue
        total = result['total_duration_seconds']
        require(close(sum(result['components'].values()), total), 'Component sum differs from route total.')
        require(close((instant(result['eta']) - cutoff).total_seconds(), total), 'Destination ETA differs from total duration.')
        expected_legs = inputs[result['id']]['legs']
        require([leg['leg_id'] for leg in result['legs']] == [leg['id'] for leg in expected_legs],
                'Estimated legs must preserve the supplied itinerary sequence.')
        cursor = cutoff
        components = {'walking_seconds': 0, 'waiting_seconds': 0, 'riding_seconds': 0}
        for leg, original in zip(result['legs'], expected_legs):
            require(leg['mode'] == original['mode'], 'Estimated leg mode changed.')
            start, end = instant(leg['start_at']), instant(leg['end_at'])
            require(close((start - cursor).total_seconds(), leg['wait_before_seconds']), 'Unaccounted gap or overlap between legs.')
            require(close((end - start).total_seconds(), leg['duration_seconds']), 'Leg time differs from duration.')
            components['waiting_seconds'] += leg['wait_before_seconds']
            components['walking_seconds' if leg['mode'] == 'WALK' else 'riding_seconds'] += leg['duration_seconds']
            uses_model = uses_model or leg['source'] == 'MODEL_CORRECTED'
            cursor = end
        require(cursor == instant(result['eta']), 'Last leg does not reach destination ETA.')
        for key in components:
            require(close(components[key], result['components'][key]), 'Leg/component mismatch: ' + key)
        uncertainty = result['uncertainty']
        if uncertainty is not None:
            require(uncertainty['lower_duration_seconds'] <= uncertainty['upper_duration_seconds'], 'Reversed uncertainty interval.')
        transit_sources = {leg['source'] for leg in result['legs'] if leg['mode'] == 'SUBWAY'}
        if result['method'] == 'MTA_REALTIME':
            require(transit_sources == {'MTA_REALTIME'}, 'MTA baseline contains unsupported or learned transit sources.')
        if result['method'] == 'MODEL_CORRECTED':
            require('MODEL_CORRECTED' in transit_sources and transit_sources <= {'MTA_REALTIME', 'MODEL_CORRECTED'},
                    'Model-corrected route has inconsistent transit sources; use MIXED for fallbacks.')
        if result['method'] == 'PROVIDER_FALLBACK':
            require(all(leg['source'] == 'PROVIDER' for leg in result['legs']), 'Provider-only fallback mixes estimate sources.')
        if result['method'] == 'MIXED':
            require(len({leg['source'] for leg in result['legs']}) > 1, 'Mixed route must identify multiple estimate sources.')
    require(uses_model == (response['model_version'] is not None), 'Model version must match actual use of model corrections.')

    by_id = {route['id']: route for route in results}
    eligible = [by_id[route['id']] for route in request['itineraries'] if by_id[route['id']]['comparison_eligible']]
    best = min(eligible, key=lambda route: route['total_duration_seconds']) if eligible else None
    current_id = request['current_itinerary_id']
    current = by_id.get(current_id)
    alternatives = [route for route in results if route['id'] != current_id]
    complete = bool(current and current['comparison_eligible'] and alternatives and all(
        route['comparison_eligible'] or route['status'] == 'INFEASIBLE' for route in alternatives))
    if current is None:
        action, recommendation, savings, complete = 'NOT_APPLICABLE', best['id'] if best else None, None, False
        reason = 'NO_CURRENT_ITINERARY'
    elif not current['comparison_eligible']:
        action, recommendation, savings, complete = 'UNDETERMINED', None, None, False
        reason = 'CURRENT_INFEASIBLE' if current['status'] == 'INFEASIBLE' else 'CURRENT_UNAVAILABLE'
    elif not alternatives:
        action, recommendation, savings, complete = 'UNDETERMINED', None, None, False
        reason = 'NO_ALTERNATIVES'
    elif best and best['total_duration_seconds'] < current['total_duration_seconds']:
        action, recommendation = 'SWITCH', best['id']
        savings = current['total_duration_seconds'] - best['total_duration_seconds']
        reason = 'FASTEST_ELIGIBLE_ALTERNATIVE'
    elif complete:
        action, recommendation, savings = 'STAY', current_id, 0
        reason = 'CURRENT_FASTEST_OR_TIED'
    else:
        action, recommendation, savings = 'UNDETERMINED', None, None
        reason = 'UNASSESSED_ALTERNATIVES'
    decision = response['decision']
    require(decision['action'] == action, 'Decision action conflicts with route coverage or estimates.')
    require(decision['recommended_itinerary_id'] == recommendation, 'Recommendation conflicts with eligible route ordering.')
    actual_savings = decision['estimated_savings_seconds']
    require(actual_savings is None if savings is None else actual_savings is not None and close(actual_savings, savings),
            'Estimated savings must compare current and recommended route at the same time.')
    require(decision['comparison_complete'] == complete, 'Incorrect comparison completeness.')
    require(decision['reason_codes'][0] == reason, 'Primary reason code conflicts with the decision case.')


def validate_case(case, schema):
    require(case['synthetic'] is True and case['request']['data_mode'] == 'simulated', 'Example must be marked simulated.')
    request, response = case['request'], case['response']
    if case['http_status'] == 200:
        schema_validate(request, 'Request', schema)
        request_invariants(request)
        schema_validate(response, 'Response', schema)
        response_invariants(request, response)
    elif case['http_status'] == 422:
        schema_validate(response, 'Error', schema)
        require(response['request_id'] == request.get('request_id'), 'Error request ID mismatch.')
        try:
            schema_validate(request, 'Request', schema)
            request_invariants(request)
        except (ValueError, ValidationError):
            pass
        else:
            raise ValueError('A 422 fixture must contain an invalid request.')
    else:
        raise ValueError('Unsupported fixture HTTP status.')


def check_local_refs(document, base_path):
    if isinstance(document, dict):
        if '$ref' in document:
            target, _, fragment = document['$ref'].partition('#')
            require('://' not in target, 'Contract refs must resolve locally.')
            file_path = base_path.parent / target if target else base_path
            current = load_json(file_path)
            for piece in fragment.lstrip('/').split('/') if fragment else []:
                current = current[piece.replace('~1', '/').replace('~0', '~')]
        for value in document.values():
            check_local_refs(value, base_path)
    elif isinstance(document, list):
        for value in document:
            check_local_refs(value, base_path)


def negative_checks(valid_case, schema):
    mutations = [
        ('duplicate itinerary', lambda c: c['request']['itineraries'].append(copy.deepcopy(c['request']['itineraries'][0]))),
        ('unknown reference', lambda c: c['request'].update(current_itinerary_id='unknown')),
        ('unsupported user state', lambda c: c['request'].update(user_state='ON_TRAIN')),
        ('naive timestamp', lambda c: c['request'].update(decision_time='2026-11-19T13:00:00')),
        ('negative duration', lambda c: c['request']['itineraries'][0]['legs'][0].update(provider_duration_seconds=-1)),
        ('future provider data', lambda c: c['request']['itineraries'][0]['provider'].update(queried_at='2026-11-20T00:00:00Z')),
        ('changed reference', lambda c: c['response'].update(current_itinerary_id='alternative')),
        ('incorrect ETA', lambda c: c['response']['itineraries'][0].update(eta='2026-11-19T14:00:00Z')),
        ('incorrect components', lambda c: c['response']['itineraries'][0]['components'].update(waiting_seconds=0)),
        ('incorrect savings', lambda c: c['response']['decision'].update(estimated_savings_seconds=1)),
        ('missing model version', lambda c: c['response'].update(model_version=None)),
        ('live fixture label', lambda c: c['response'].update(data_mode='live')),
        ('misleading baseline provenance', lambda c: c['response']['itineraries'][0].update(method='MTA_REALTIME')),
        ('misleading decision reason', lambda c: c['response']['decision'].update(reason_codes=['NO_ALTERNATIVES'])),
        ('infinite duration', lambda c: c['request']['itineraries'][0]['legs'][0].update(provider_duration_seconds=float('inf'))),
        ('invalid offset minutes', lambda c: c['request'].update(decision_time='2026-11-19T13:00:00+00:60')),
        ('future feed collection', lambda c: c['response']['data_status']['train_feed'].update(fetched_at='2026-11-19T13:00:01Z')),
    ]
    for name, mutate in mutations:
        case = copy.deepcopy(valid_case)
        mutate(case)
        try:
            validate_case(case, schema)
        except (ValueError, ValidationError):
            continue
        raise ValueError('Invalid mutation was accepted: ' + name)
    return len(mutations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true', help='Also reject deliberately invalid boundary examples.')
    args = parser.parse_args()
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    check_local_refs(schema, SCHEMA_PATH)
    openapi_path = ROOT / 'contracts' / 'openapi.json'
    openapi = load_json(openapi_path)
    require(openapi['openapi'] == '3.1.0', 'Unexpected OpenAPI version.')
    check_local_refs(openapi, openapi_path)
    cases = []
    for path in sorted((ROOT / 'examples').glob('*.json')):
        case = load_json(path)
        validate_case(case, schema)
        cases.append(case)
        print('PASS ' + path.name)
    require(cases, 'No contract examples found.')
    print(f'Validated JSON Schema, local OpenAPI references, and {len(cases)} simulated scenarios.')
    if args.self_test:
        count = negative_checks(cases[0], schema)
        print(f'Rejected {count} deliberately invalid contract mutations.')


if __name__ == '__main__':
    main()
