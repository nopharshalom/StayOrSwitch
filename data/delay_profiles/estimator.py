"""Read frozen historical profiles without fitting or inspecting outcomes."""

from .common import context_fields, digest, group_candidates, horizon_group, read_json


class ProfileEstimator:
    def __init__(self, profile_path):
        self.profile = read_json(profile_path) if not isinstance(profile_path, dict) else profile_path
        if self.profile.get("schema_version") != "delay-profiles-v1":
            raise ValueError("Unsupported historical profile schema.")
        payload = {key: value for key, value in self.profile.items() if key != "seal"}
        if self.profile.get("seal") != digest(payload):
            raise ValueError("Historical profile seal does not match its content.")
        self.config = self.profile["configuration"]
        self.groups = self.profile["groups"]
        self.seal = self.profile["seal"]
        self.fit_split = self.profile["fit_split"]
        if self.fit_split != "train":
            raise ValueError("Only a frozen training profile can be used for prediction.")

    def estimate(self, target, route_id, from_stop_id, to_stop_id, cutoff, horizon_seconds, context):
        requested_state = context_fields(context)[0]
        result = {"correction_seconds": 0.0, "supported": False, "incident_supported": False,
                  "level": "MTA_FALLBACK", "event_count": 0, "incident_count": 0,
                  "statistics": None, "reason": "INSUFFICIENT_HISTORICAL_SUPPORT",
                  "context_requested": requested_state, "context_used": None,
                  "profile_seal": self.seal, "fit_split": self.fit_split}
        if horizon_group(horizon_seconds) in {"EXPIRED", "UNAVAILABLE"}:
            return dict(result, reason="EXPIRED_OR_INVALID_FORECAST")
        for level, key, identity in group_candidates(target, route_id, from_stop_id, to_stop_id,
                                                     cutoff, horizon_seconds, context, self.config):
            group = self.groups.get(key)
            if group is None or group["event_count"] < self.config["min_profile_events"]:
                continue
            if identity["state"] == "SEVERE" and group["incident_count"] < self.config["min_severe_incidents"]:
                continue
            incident_supported = identity["state"] in {"SEVERE", "DISRUPTION"}
            fallback = requested_state in {"SEVERE", "DISRUPTION"} and identity["state"] == "ANY"
            return dict(result, correction_seconds=group["statistics"]["mean_signed_seconds"],
                        supported=True, incident_supported=incident_supported, level=level,
                        event_count=group["event_count"], incident_count=group["incident_count"],
                        statistics=group["statistics"], context_used=identity["state"],
                        reason="INCIDENT_SUPPORT_INSUFFICIENT_USING_TIME_PROFILE" if fallback else None,
                        group=identity)
        return result
