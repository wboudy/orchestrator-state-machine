from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from watcher.policy_defaults import EffectivePolicySnapshot, PolicyDefaultsError, inject_canonical_defaults
from watcher.policy_precedence import PRECEDENCE_ORDER as SPEC_PRECEDENCE_ORDER


@dataclass(frozen=True)
class PolicyVerifierFinding:
    code: str
    message: str


@dataclass(frozen=True)
class PolicyVerificationResult:
    snapshot: EffectivePolicySnapshot | None
    errors: Tuple[PolicyVerifierFinding, ...]
    warnings: Tuple[PolicyVerifierFinding, ...]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


class PolicyVerificationError(ValueError):
    def __init__(self, errors: Sequence[PolicyVerifierFinding]):
        self.errors = tuple(errors)
        joined = "; ".join(f"{entry.code}:{entry.message}" for entry in self.errors)
        super().__init__("POLICY_VERIFY_FAILED: " + joined)


def verify_policy_static(
    raw_policy: Dict[str, Any] | None,
    *,
    precedence_order: Sequence[str] = SPEC_PRECEDENCE_ORDER,
) -> PolicyVerificationResult:
    errors: List[PolicyVerifierFinding] = []
    warnings: List[PolicyVerifierFinding] = []

    try:
        snapshot = inject_canonical_defaults(raw_policy)
    except PolicyDefaultsError as exc:
        for message in exc.errors:
            errors.append(
                PolicyVerifierFinding(
                    code="policy_invalid",
                    message=message,
                )
            )
        return PolicyVerificationResult(snapshot=None, errors=tuple(errors), warnings=tuple(warnings))

    policy = snapshot.effective_policy

    max_retries = int(policy["retry"]["max_retries"])
    if max_retries < 1:
        errors.append(
            PolicyVerifierFinding(
                code="unreachable_state",
                message="RETRY_WAIT is unreachable when retry.max_retries < 1",
            )
        )

    day_cap = int(policy["risk_budget"]["max_noncritical_escalations_per_day"])
    hour_cap = int(policy["risk_budget"]["max_noncritical_pages_per_hour"])
    if day_cap == 0 and hour_cap > 0:
        errors.append(
            PolicyVerifierFinding(
                code="escalation_conflict",
                message=(
                    "risk_budget conflict: max_noncritical_escalations_per_day=0 "
                    "cannot coexist with max_noncritical_pages_per_hour>0"
                ),
            )
        )

    errors.extend(_check_precedence_order(precedence_order))

    return PolicyVerificationResult(
        snapshot=snapshot,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def verify_policy_or_raise(
    raw_policy: Dict[str, Any] | None,
    *,
    precedence_order: Sequence[str] = SPEC_PRECEDENCE_ORDER,
) -> PolicyVerificationResult:
    result = verify_policy_static(raw_policy, precedence_order=precedence_order)
    if result.errors:
        raise PolicyVerificationError(result.errors)
    return result


def _check_precedence_order(precedence_order: Sequence[str]) -> List[PolicyVerifierFinding]:
    findings: List[PolicyVerifierFinding] = []
    provided = tuple(precedence_order)

    if len(set(provided)) != len(provided):
        findings.append(
            PolicyVerifierFinding(
                code="precedence_ambiguous",
                message="precedence order contains duplicate steps",
            )
        )
        return findings

    missing = [item for item in SPEC_PRECEDENCE_ORDER if item not in provided]
    extras = [item for item in provided if item not in SPEC_PRECEDENCE_ORDER]
    if missing or extras:
        detail_parts = []
        if missing:
            detail_parts.append("missing=" + ",".join(missing))
        if extras:
            detail_parts.append("unknown=" + ",".join(extras))
        findings.append(
            PolicyVerifierFinding(
                code="precedence_ambiguous",
                message="precedence steps mismatch: " + " ".join(detail_parts),
            )
        )
        return findings

    if provided != SPEC_PRECEDENCE_ORDER:
        findings.append(
            PolicyVerifierFinding(
                code="precedence_ambiguous",
                message="precedence order does not match spec order",
            )
        )
    return findings
