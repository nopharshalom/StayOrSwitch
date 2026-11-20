#!/usr/bin/env python3
"""Independently audit eight frozen route-execution examples without rescoring."""

from pathlib import Path
import gzip,json,hashlib,math,collections,datetime
ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'algo/reports/november-repair-test.json'
SHARED=ROOT/'algo/local/november-repair/shared-route-execution.json.gz'
INDEX=ROOT/'data/processed/november-repair-v2/route-events.json.gz'
MANIFEST=ROOT/'data/manifests/november-2026.json'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(1024*1024),b''): h.update(x)
 return h.hexdigest()
def epoch(v):
 if isinstance(v,(float,int)): return float(v)
 if isinstance(v,str): return datetime.datetime.fromisoformat(v.replace('Z','+00:00')).timestamp()
 return None
def stream_events(path):
 decoder=json.JSONDecoder(); buf=''; marker='"events":['
 with gzip.open(path,'rt') as f:
  while marker not in buf:
   c=f.read(65536)
   if not c: raise AssertionError('No events array')
   buf+=c
  buf=buf.split(marker,1)[1]
  while True:
   buf=buf.lstrip(' \r\n,')
   if buf.startswith(']'): return
   try: value,n=decoder.raw_decode(buf)
   except json.JSONDecodeError:
    c=f.read(65536)
    if not c: raise
    buf+=c;continue
   yield value;buf=buf[n:]
r=json.loads(REPORT.read_text())
SHARED=ROOT/r['shared_route_execution']['path']
sr=json.load(gzip.open(SHARED,'rt'))
INDEX=ROOT/sr['archive']['archive']['path']
sm={x['case_id']:x['outcomes'] for x in sr['cases']}; cm={c['id']:c for c in r['cases']}
templates={t['id']:t for c in r['corridors'] for t in c['routes']}
specs=[
 ('paired_model_gain','timesquare_boroughhall--lmm-alert-274848--1793803238596',None),
 ('paired_model_loss','timesquare_boroughhall--lmm-alert-275196--1793996883604',None),
 ('old_selected_train_missed_route_completed','timesquare_boroughhall--lmm-alert-274576--1793641628577','google-route-b4b074fe878e8f48c76e1617'),
 ('model_switch_loses_to_own_stay','pilot_hayden_tandon--lmm-alert-274525--1793615892737',None),
 ('severe_switch_unresolved','portauthority_tandon--lmm-alert-274566--1793635162704',None),
 ('unresolved_origin_evidence','timesquare_boroughhall--lmm-alert-274517--1793603458612','google-route-286854e95fde76a2b52d9bf9'),
 ('first_train_arrival_unusable','timesquare_boroughhall--lmm-alert-275830--1794405620554',None),
 ('source_coverage_gap','courtsquare_timessquare--lmm-alert-274534--1793622093585',None),
]
queries=[]; examples=[]
for purpose,cid,explicit in specs:
 c=cm[cid]; mode=c['modes']['incident_profile']; decision=mode['strict_decision']; ids=[explicit or decision['recommended_itinerary_id']]
 if purpose.startswith('paired_'): ids=list(dict.fromkeys([c['paired_policies']['incident_vs_mta']['baseline_route_id'],c['paired_policies']['incident_vs_mta']['model_route_id']]))
 if purpose=='model_switch_loses_to_own_stay': ids=list(dict.fromkeys([c['reference_route_id'],decision['recommended_itinerary_id']]))
 x={'purpose':purpose,'case_id':cid,'local_time':c['local_time'],'corridor_id':c['corridor_id'],'decision_at':c['decision_at'],'routes':[]}
 for rid in ids:
  out=sm[cid][rid]; t=templates[rid]
  x['routes'].append({'route_id':rid,'route_name':t['name'],'outcome':out})
  for leg in t['legs']:
   queries.append({'case_id':cid,'route_id':rid,'leg':leg,'start':c['decision_at']-120,'end':c['decision_at']+7200})
 examples.append(x)
keys={(q['leg']['feed_id'],line,q['leg']['from_stop_id'],q['leg']['to_stop_id']) for q in queries for line in q['leg'].get('route_ids',[q['leg']['route_id']])}
events={}; scanned=0
for e in stream_events(INDEX):
 scanned+=1;k=(e['feed_id'],e['route_id'],e['from_stop_id'],e['to_stop_id'])
 if k not in keys: continue
 if not any(q['leg']['feed_id']==e['feed_id'] and e['route_id'] in q['leg'].get('route_ids',[q['leg']['route_id']]) and q['leg']['from_stop_id']==e['from_stop_id'] and q['leg']['to_stop_id']==e['to_stop_id'] and ((e['departure_at'] is not None and q['start']+120<=e['departure_at']<=q['end']) or (e['departure_at'] is None and e['last_observed_at']>=q['start'] and e['first_observed_at']<=q['end'])) for q in queries):continue
 events[(e['canonical_trip_id'],e['from_stop_id'],e['to_stop_id'])]=e
print('EVENTS',scanned,len(events),flush=True)
checks=collections.Counter(); needed_aliases=set(); snapshots_needed={}; endpoint_targets={}; blocker_reviews=[]; detail=[]
def check(condition,name):
 assert condition,name;checks[name]+=1
check(sha(SHARED)==r['shared_route_execution']['sha256'],'shared_cache_report_binding')
check(sha(INDEX)==sr['archive']['archive']['sha256'],'archive_shared_cache_binding')
check(sha(ROOT/sr['archive']['manifest']['path'])==sr['archive']['manifest']['sha256'],'archive_manifest_binding')
def event_of(row):return events[(row['canonical_trip_id'],row['from_stop_id'],row['to_stop_id'])]
def require_observation(e,ob):
 check(ob in e['observations'],'exact_index_observation')
 snapshots_needed[(e['feed_id'],ob['at'])]=(e,ob)
def require_endpoints(e):
 for alias in e['trip_aliases']:
  needed_aliases.add(alias)
  for stop in (e['from_stop_id'],e['to_stop_id']):endpoint_targets[(alias,stop)]=e
for x in examples:
 for item in x['routes']:
  o=item['outcome'];t=templates[item['route_id']];ready=x['decision_at']+t['access_walk_seconds']; walk=t['access_walk_seconds']+sum(t['transfer_walk_seconds'])+t['egress_walk_seconds'];wait=ride=0
  for j,legout in enumerate(o.get('selected_legs',o.get('completed_legs',[]))):
   e=event_of(legout);require_endpoints(e);require_observation(e,legout['boarding_observation'])
   dep,arr=e['departure_at'],e['arrival_at'];ob=legout['boarding_observation'];check(dep==legout['departure_at'] and arr==legout['arrival_at'],'endpoint_equality');check(dep>=ready and arr>=dep,'chronology');check(abs(legout['platform_ready_at']-ready)<1e-6,'ready_arithmetic');check(ob['at']<=dep and ob['source_at']<=ob['at'] and dep-ob['source_at']<=120,'boarding_freshness');check(ob.get('valid_until_at') is None or dep<ob['valid_until_at'],'not_superseded');check(ob['path_status']=='COMPATIBLE','compatible_before_boarding')
   allowed=t['legs'][j].get('route_ids',[t['legs'][j]['route_id']]);known=[];unknown=[]
   for ee in events.values():
    if ee['feed_id']!=e['feed_id'] or ee['route_id'] not in allowed or ee['from_stop_id']!=e['from_stop_id'] or ee['to_stop_id']!=e['to_stop_id']:continue
    dd=ee['departure_at']; rows=[z for z in ee['observations'] if x['decision_at']-120<=z['at']<=dep]
    if dd is None:
     if ee['arrival_at'] is not None and ee['arrival_at']<ready:continue
     if any(z['path_status']!='INCOMPATIBLE' or z['source_at'] is None or z['at']-z['source_at']>120 for z in rows):unknown.append(ee['canonical_trip_id'])
    elif ready<=dd<=dep:
     prior=[z for z in ee['observations'] if z['at']<=dd]
     if not prior: unknown.append(ee['canonical_trip_id']);continue
     z=max(prior,key=lambda z:z['at'])
     if dd-z['at']>120 or z['source_at'] is None or dd-z['source_at']>120 or z.get('valid_until_at') is not None and dd>=z['valid_until_at'] or z['path_status']=='UNKNOWN': unknown.append(ee['canonical_trip_id'])
     elif z['path_status']=='COMPATIBLE':known.append((dd,ee['canonical_trip_id']))
   check(not unknown,'no_unresolved_earlier_candidate_for_inferred_leg');check(sorted(known)==[(dep,e['canonical_trip_id'])],'first_compatible_departure_no_oracle')
   wait+=dep-ready;ride+=arr-dep;ready=arr+(t['transfer_walk_seconds'][j] if j<len(t['transfer_walk_seconds']) else t['egress_walk_seconds'])
  if o['status']=='INFERRED':
   check(abs(ready-o['destination_arrival_at'])<1e-6,'destination_arithmetic');check(abs(walk+wait+ride-o['total_duration_seconds'])<1e-6,'duration_components');check(o['total_duration_seconds']<=7200,'horizon')
  if 'event' in o:
   e=event_of(o['event']);require_endpoints(e);require_observation(e,o['boarding_observation']);check(e['arrival_at'] is None,'first_arrival_remains_unusable')
  if o.get('reason')=='UNRESOLVED_EARLIER_BOARDING':
   reviews=[]
   for b in o['possible_earlier_boardings']:
    e=event_of(b);require_endpoints(e);obs=[z for z in e['observations'] if o['observation_start_at']<=z['at']<=o['selection_diagnostics']['coverage']['last_capture_at']+120]
    active=[z for z in obs if z['path_status']!='INCOMPATIBLE']
    check(bool(active),'blocker_has_unresolved_or_compatible_observation')
    z=active[0];require_observation(e,z)
    bef=[z for z in obs if z['at']<=o['platform_ready_at']];latest=max(bef,key=lambda z:z['at']) if bef else None
    review={'canonical_trip_id':e['canonical_trip_id'],'blocker_reason':b['blocker_reason'],'endpoint_flags':e['endpoint_flags'],'first_relevant_observation':z,'latest_before_ready':latest,'compatible_then_explicit_incompatible_before_ready':bool(latest and latest['path_status']=='INCOMPATIBLE' and any(y['path_status']=='COMPATIBLE' and y['at']<latest['at'] for y in bef)),'raw_departure_forecast_ahead_of_ready_seconds':None if z['departure_forecast_at'] is None else z['departure_forecast_at']-o['platform_ready_at']}
    reviews.append(review)
   item['independent_blocker_review']=reviews;blocker_reviews+=reviews
  if o.get('reason')=='INSUFFICIENT_FEED_COVERAGE':
   for gap in o['coverage']['gaps']:
    if gap['reason']=='UNUSABLE_ARCHIVED_SNAPSHOT': snapshots_needed[(t['legs'][o['leg_index']]['feed_id'],gap['start'])]=('GAP',gap)
  detail.append({'case_id':x['case_id'],'route_id':item['route_id'],'status':o['status'],'reason':o.get('reason'),'duration_seconds':o.get('total_duration_seconds')})
print('TARGETS',len(endpoint_targets),len(snapshots_needed),flush=True)
manifest=json.loads(MANIFEST.read_text()); label_records={}; source_bindings={}
for item in manifest['daily_labels'].values():
 p=ROOT/item['path']; rows=json.load(gzip.open(p,'rt')); wanted=needed_aliases.intersection(rows)
 if not wanted:continue
 check(sha(p)==item['sha256'],'label_source_hash');source_bindings[item['path']]=item['sha256']
 for alias in wanted:
  for stop,label in rows[alias].items():
   if (alias,stop) in endpoint_targets: label_records[(alias,stop)]=label
for (alias,stop),e in endpoint_targets.items():
 label=label_records.get((alias,stop))
 if not label: continue
 check(label['canonical_event_trip_id']==e['canonical_trip_id'],'label_canonical_identity');check(label['stop_id']==stop,'label_stop_identity')
 endpoint='departure' if stop==e['from_stop_id'] else 'arrival';value=e[endpoint+'_at']
 if value is not None:
  check(epoch(label[endpoint+'_at'])==value,'original_label_time');check(label[endpoint+'_usable'] and not label.get('quality_flags') and not label.get(endpoint+'_quality_flags'),'original_endpoint_quality');check(label['confirmation_status']=='CONFIRMED' and epoch(label['confirmed_at']) is not None,'confirmation');check(abs(epoch(label['stop_last_observed_at'])-value)<=180,'endpoint_age')
 else:
  reasons=label.get('quality_flags',[])+label.get(endpoint+'_quality_flags',[])
  eligible=label.get(endpoint+'_usable') and not reasons and label.get('confirmation_status')=='CONFIRMED' and epoch(label.get('confirmed_at')) is not None and epoch(label.get('stop_last_observed_at')) is not None and epoch(label.get(endpoint+'_at')) is not None and abs(epoch(label['stop_last_observed_at'])-epoch(label[endpoint+'_at']))<=180
  check(not eligible or 'CONFLICTING_CANONICAL_ALIAS_ENDPOINTS' in e['endpoint_flags']['boarding' if endpoint=='departure' else 'alighting'],'unusable_endpoint_exclusion_explained')
found=set();needed_days={datetime.datetime.fromtimestamp(at,datetime.timezone.utc).date().isoformat() for _,at in snapshots_needed}
for day in manifest['days']:
 if day['date'] not in needed_days:continue
 item=day['outputs']['snapshots'];p=ROOT/item['path'];check(sha(p)==item['sha256'],'snapshot_source_hash');source_bindings[item['path']]=item['sha256']
 with gzip.open(p,'rt') as f:
  for line in f:
   s=json.loads(line);k=(s.get('feed_id'),s.get('captured_at'))
   if k not in snapshots_needed:continue
   found.add(k);e,ob=snapshots_needed[k]
   if e=='GAP':check(s.get('status') not in ['AVAILABLE','FRESH'] or s.get('replay_freshness')!='FRESH','original_gap_snapshot');continue
   check(s.get('sha256')==ob['snapshot_sha256'],'original_snapshot_hash');ts=[t for t in s.get('trips',[]) if t.get('id')==ob['trip_id']];check(len(ts)==1,'original_trip_identity');t=ts[0];check(t['route_id']==e['route_id'],'original_actual_route');ss=t.get('stop_updates',[]);a=[i for i,v in enumerate(ss) if v.get('stop_id')==e['from_stop_id']];b=[i for i,v in enumerate(ss) if v.get('stop_id')==e['to_stop_id']]
   if ob['path_status']=='COMPATIBLE':
    check(len(a)==len(b)==1 and a[0]<b[0],'original_ordered_path');check(epoch(ss[a[0]].get('departure_time'))==ob['departure_forecast_at'],'original_departure_forecast');check(epoch(ss[b[0]].get('arrival_time'))==ob['arrival_forecast_at'],'original_arrival_forecast')
check(found==set(snapshots_needed),'all_requested_source_snapshots_found')
# Recompute the two policy comparisons and one own-Stay comparison.
for x in examples:
 if len(x['routes'])==2:
  a,b=[i['outcome']['total_duration_seconds'] for i in x['routes']];difference=a-b;x['independent_gain_seconds']=difference
  expected=cm[x['case_id']]['paired_policies']['incident_vs_mta']['gain_seconds'] if x['purpose'].startswith('paired_') else cm[x['case_id']]['modes']['incident_profile']['scores']['inferred_switch_savings_seconds']
  check(abs(difference-expected)<1e-6,'comparison_gain_arithmetic')
old=json.loads((ROOT/'algo/reports/november-weekday-operational-diagnostics.json').read_text());selected=examples[2];miss=next(x for x in old['model_misses']['cases'] if x['case_id']==selected['case_id'] and x['model_route_id']==selected['routes'][0]['route_id']);check(miss['missed_boarding_seconds']>0,'old_selected_train_miss');check(selected['routes'][0]['outcome']['status']=='INFERRED','old_miss_route_completed');selected['original_missed_train_diagnostic']=miss
out={'schema_version':'november-repair-execution-example-independent-audit-v1','status':'PASS','audit_selection':'Eight purpose-selected post-scoring checks, not an extra performance sample. Includes positive/negative comparisons, an old missed-train route completion, severe and other unresolved evidence, first-arrival exclusion, and a feed gap.','checks':dict(checks),'total_checks':sum(checks.values()),'case_count':len(examples),'route_outcome_count':len(detail),'index_events_scanned':scanned,'index_events_retained_for_independent_ordering':len(events),'source_snapshots_checked':len(found),'original_label_records_checked':len(label_records),'sources':{'audit_script':sha(Path(__file__)), 'old_operational_diagnostic':sha(ROOT/'algo/reports/november-weekday-operational-diagnostics.json'), 'report':sha(REPORT),'shared_route_execution':sha(SHARED),'archive_index':sha(INDEX),'source_manifest':sha(MANIFEST)},'verified_source_files':source_bindings,'blocker_interpretation':{'numerical_future_etas_are_not_proof_of_actual_boarding_order':True,'explicitly_incompatible_after_earlier_compatible_before_ready_in_sample':sum(x['compatible_then_explicit_incompatible_before_ready'] for x in blocker_reviews),'largest_first_relevant_departure_forecast_ahead_seconds':max([x['raw_departure_forecast_ahead_of_ready_seconds'] for x in blocker_reviews if x['raw_departure_forecast_ahead_of_ready_seconds'] is not None],default=None),'raw_empty_stop_cancellation_coverage_was_not_claimed':True},'examples':examples,'outcome_inventory':detail,'limitations':['This audit checks existing final MTA prediction proxies, not independently measured passenger arrivals.','Eight selected examples establish local consistency, not an algorithm success rate.','Unknown train order can remain unresolved despite an apparently distant ETA; that ETA is not a confirmed departure.','No broad raw CSV/GTFS-RT re-ingestion was performed; exact screened labels and original normalized snapshots are verified against their source-manifest hashes.']}
path=ROOT/'algo/reports/november-repair-execution-example-audit.json';path.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('PASS',sum(checks.values()),'sha',sha(path),flush=True)
