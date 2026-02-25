# Incident Cluster Digest Builder Contract

Builds daily digest records with cluster ranking from incidents.

## Cluster Scoring (Section 17.3)

`score = priority_weight + spread_weight + age_weight + human_weight`

- `priority_weight`: `P0=8, P1=5, P2=3, P3=1, P4=0`
- `spread_weight`: count of unique origin beads in cluster
- `age_weight`: `min(cluster_age_days, 7)`
- `human_weight`: `2 * unresolved_needs_human_count`

Higher score sorts earlier.

## Digest Output (Section 23.4)

- `date_local`
- `timezone`
- `new_escalations`
- `dead_letter_count`
- `clusters` (sorted desc by score)
- `suppressed_by_dedupe`
- `deferred_by_budget`

## Validation

- Incident priorities must be `0..4`.
- Incident timestamps must be timezone-aware.
- Digest timezone must be valid IANA name.
