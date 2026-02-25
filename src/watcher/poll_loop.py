from dataclasses import dataclass
import time
from typing import Callable, Iterable, List, Sequence

from watcher.handoff_parser import HandoffValidationError, parse_handoff_block


DEFAULT_POLL_SECONDS = 15


@dataclass(frozen=True)
class BeadSnapshot:
    bead_id: str
    priority: int
    updated_at: str
    labels: Sequence[str]
    notes_text: str


def is_eligible_queued(snapshot: BeadSnapshot) -> bool:
    label_set = set(snapshot.labels)

    if "needs:orchestrator" not in label_set:
        return False
    if "orchestrator:running" in label_set:
        return False
    if "needs:human" in label_set:
        return False
    if "orchestrator:done" in label_set:
        return False

    try:
        parse_handoff_block(snapshot.notes_text)
    except HandoffValidationError:
        return False

    return True


def select_eligible_queued(
    snapshots: Iterable[BeadSnapshot],
    limit: int = 20,
) -> List[BeadSnapshot]:
    if limit <= 0:
        return []

    eligible = [snapshot for snapshot in snapshots if is_eligible_queued(snapshot)]
    eligible.sort(key=lambda item: (item.priority, item.updated_at, item.bead_id))
    return eligible[:limit]


def poll_once(
    fetch_snapshots: Callable[[], Sequence[BeadSnapshot]],
    limit: int = 20,
) -> List[BeadSnapshot]:
    return select_eligible_queued(fetch_snapshots(), limit=limit)


def poll_loop(
    fetch_snapshots: Callable[[], Sequence[BeadSnapshot]],
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    limit: int = 20,
    max_cycles: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
):
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be > 0")
    if max_cycles is not None and max_cycles <= 0:
        raise ValueError("max_cycles must be > 0 when set")

    cycles = 0
    while True:
        yield poll_once(fetch_snapshots, limit=limit)
        cycles += 1

        if max_cycles is not None and cycles >= max_cycles:
            break

        sleep_fn(poll_seconds)

