from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PRIORITY_WEIGHTS = {
    0: 8,
    1: 5,
    2: 3,
    3: 1,
    4: 0,
}


@dataclass(frozen=True)
class IncidentRecord:
    incident_id: str
    error_signature: str
    origin_id: str
    priority: int
    created_at_utc: datetime
    unresolved_needs_human: bool
    dead_letter: bool
    suppressed_by_dedupe: bool
    deferred_by_budget: bool


@dataclass(frozen=True)
class IncidentCluster:
    error_signature: str
    incident_ids: List[str]
    unique_origin_count: int
    cluster_age_days: int
    unresolved_needs_human_count: int
    priority_weight: int
    spread_weight: int
    age_weight: int
    human_weight: int
    score: int


@dataclass(frozen=True)
class DailyDigestRecord:
    date_local: str
    timezone: str
    new_escalations: int
    dead_letter_count: int
    clusters: List[IncidentCluster]
    suppressed_by_dedupe: int
    deferred_by_budget: int


class DigestBuilderError(ValueError):
    pass


def build_daily_digest(
    *,
    incidents: Iterable[IncidentRecord],
    now_utc: datetime,
    timezone_name: str,
) -> DailyDigestRecord:
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise DigestBuilderError("now_utc must be timezone-aware")

    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise DigestBuilderError(f"invalid timezone: {timezone_name}") from exc

    now = now_utc.astimezone(timezone.utc)
    local_date = now.astimezone(tz).strftime("%Y-%m-%d")
    items = list(incidents)

    clusters = _build_clusters(items, now)
    clusters.sort(key=lambda cluster: (-cluster.score, cluster.error_signature))

    new_escalations = sum(1 for incident in items if incident.unresolved_needs_human)
    dead_letter_count = sum(1 for incident in items if incident.dead_letter)
    suppressed_by_dedupe = sum(1 for incident in items if incident.suppressed_by_dedupe)
    deferred_by_budget = sum(1 for incident in items if incident.deferred_by_budget)

    return DailyDigestRecord(
        date_local=local_date,
        timezone=timezone_name,
        new_escalations=new_escalations,
        dead_letter_count=dead_letter_count,
        clusters=clusters,
        suppressed_by_dedupe=suppressed_by_dedupe,
        deferred_by_budget=deferred_by_budget,
    )


def _build_clusters(incidents: List[IncidentRecord], now_utc: datetime) -> List[IncidentCluster]:
    grouped: Dict[str, List[IncidentRecord]] = {}
    for incident in incidents:
        _validate_incident(incident)
        grouped.setdefault(incident.error_signature, []).append(incident)

    clusters: List[IncidentCluster] = []
    for signature, members in grouped.items():
        unique_origins = {incident.origin_id for incident in members}
        earliest = min(incident.created_at_utc.astimezone(timezone.utc) for incident in members)
        age_days = max(0, (now_utc - earliest).days)
        unresolved_count = sum(1 for incident in members if incident.unresolved_needs_human)
        priority_weight = max(PRIORITY_WEIGHTS[incident.priority] for incident in members)
        spread_weight = len(unique_origins)
        age_weight = min(age_days, 7)
        human_weight = 2 * unresolved_count
        score = priority_weight + spread_weight + age_weight + human_weight

        clusters.append(
            IncidentCluster(
                error_signature=signature,
                incident_ids=sorted(incident.incident_id for incident in members),
                unique_origin_count=spread_weight,
                cluster_age_days=age_days,
                unresolved_needs_human_count=unresolved_count,
                priority_weight=priority_weight,
                spread_weight=spread_weight,
                age_weight=age_weight,
                human_weight=human_weight,
                score=score,
            )
        )
    return clusters


def _validate_incident(incident: IncidentRecord) -> None:
    if not incident.incident_id:
        raise DigestBuilderError("incident_id required")
    if not incident.error_signature:
        raise DigestBuilderError("error_signature required")
    if not incident.origin_id:
        raise DigestBuilderError("origin_id required")
    if incident.priority not in PRIORITY_WEIGHTS:
        raise DigestBuilderError(f"invalid priority: {incident.priority}")
    if incident.created_at_utc.tzinfo is None or incident.created_at_utc.utcoffset() is None:
        raise DigestBuilderError("incident created_at_utc must be timezone-aware")
