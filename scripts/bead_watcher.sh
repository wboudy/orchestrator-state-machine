#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage: scripts/bead_watcher.sh [--once]

Runs a finite-state automation loop:
1) pick next ready bead
2) invoke codex exec for exactly that bead
3) verify bead status and retry/escalate if needed
4) stop when no ready beads remain

Options:
  --once      Process at most one bead cycle, then exit
  --help      Show this help

Environment variables:
  MODEL                     Codex model (default: gpt-5-mini)
  MAX_CYCLES                Hard cap on cycles (default: 200)
  MAX_RETRIES_PER_ISSUE     Retries before escalation (default: 3)
  MAX_NO_PROGRESS_CYCLES    Repeated unchanged queue cap (default: 8)
  MAX_CONSECUTIVE_FAILURES  Hard failure streak cap (default: 5)
  SLEEP_SECONDS             Delay between cycles (default: 5)
  CODEX_SANDBOX             Codex sandbox mode (default: workspace-write)
  CODEX_APPROVAL            Codex approval mode (default: never)
  CODEX_SESSION_ID          Resume this Codex session id each cycle (default: empty)
  CODEX_RESUME_LAST         If 1, use codex exec resume --last when session id empty
  HUMAN_ESCALATION_CMD      Optional shell command for human escalation
  QUIET_HOURS_START         Quiet hours start (0-23, default: 22)
  QUIET_HOURS_END           Quiet hours end (0-23, default: 8)
  LOG_DIR                   Log directory (default: .automation/logs)
EOF
}

ONCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --once)
      ONCE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

for cmd in bd codex jq git; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

MODEL="${MODEL:-gpt-5-mini}"
MAX_CYCLES="${MAX_CYCLES:-200}"
MAX_RETRIES_PER_ISSUE="${MAX_RETRIES_PER_ISSUE:-3}"
MAX_NO_PROGRESS_CYCLES="${MAX_NO_PROGRESS_CYCLES:-8}"
MAX_CONSECUTIVE_FAILURES="${MAX_CONSECUTIVE_FAILURES:-5}"
SLEEP_SECONDS="${SLEEP_SECONDS:-5}"
CODEX_SANDBOX="${CODEX_SANDBOX:-workspace-write}"
CODEX_APPROVAL="${CODEX_APPROVAL:-never}"
CODEX_SESSION_ID="${CODEX_SESSION_ID:-}"
CODEX_RESUME_LAST="${CODEX_RESUME_LAST:-0}"
HUMAN_ESCALATION_CMD="${HUMAN_ESCALATION_CMD:-}"
QUIET_HOURS_START="${QUIET_HOURS_START:-22}"
QUIET_HOURS_END="${QUIET_HOURS_END:-8}"
LOG_DIR="${LOG_DIR:-.automation/logs}"

mkdir -p "$LOG_DIR"

log() {
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

ready_snapshot() {
  bd ready --json --limit 200 | jq -r '[.[] | select(.issue_type != "epic") | .id] | sort | join(",")'
}

next_ready_issue() {
  bd ready --json --limit 200 | jq -r '[.[] | select(.issue_type != "epic")][0].id // empty'
}

in_quiet_hours() {
  local hour
  hour="$(date +%H)"
  hour="${hour#0}"
  if [[ "$QUIET_HOURS_START" -eq "$QUIET_HOURS_END" ]]; then
    return 1
  fi
  if [[ "$QUIET_HOURS_START" -lt "$QUIET_HOURS_END" ]]; then
    [[ "$hour" -ge "$QUIET_HOURS_START" && "$hour" -lt "$QUIET_HOURS_END" ]]
  else
    [[ "$hour" -ge "$QUIET_HOURS_START" || "$hour" -lt "$QUIET_HOURS_END" ]]
  fi
}

maybe_notify_human() {
  local issue_id="$1"
  local escalation_id="$2"
  if [[ -z "$HUMAN_ESCALATION_CMD" ]]; then
    return 0
  fi
  if in_quiet_hours; then
    log "Quiet hours active; skipping HUMAN_ESCALATION_CMD for $issue_id"
    return 0
  fi
  log "Running HUMAN_ESCALATION_CMD for issue=$issue_id escalation=$escalation_id"
  WATCHER_ISSUE_ID="$issue_id" WATCHER_ESCALATION_ID="$escalation_id" bash -lc "$HUMAN_ESCALATION_CMD" || true
}

declare -A retries=()
consecutive_failures=0
no_progress_cycles=0
last_snapshot=""

for ((cycle = 1; cycle <= MAX_CYCLES; cycle++)); do
  snapshot_before="$(ready_snapshot)"
  issue_id="$(next_ready_issue)"

  if [[ -z "$issue_id" ]]; then
    log "No ready beads remain. Stopping watcher."
    exit 0
  fi

  log "Cycle $cycle: selected $issue_id"
  attempts="${retries[$issue_id]:-0}"

  if [[ "$attempts" -ge "$MAX_RETRIES_PER_ISSUE" ]]; then
    esc_title="Human escalation: $issue_id exceeded watcher retries"
    esc_desc="Watcher reached $MAX_RETRIES_PER_ISSUE retries for $issue_id without closure/block transition. Human decision required."
    escalation_id="$(bd create "$esc_title" --type task --priority 1 --labels escalation,human --description "$esc_desc" --silent)"
    bd dep add "$issue_id" "$escalation_id" >/dev/null
    bd update "$issue_id" --status blocked --notes "Auto-blocked by watcher after retry exhaustion; see $escalation_id for human decision." >/dev/null
    maybe_notify_human "$issue_id" "$escalation_id"
    log "Blocked $issue_id after retry exhaustion and created escalation bead $escalation_id"
    unset 'retries[$issue_id]'
    consecutive_failures=0
    continue
  fi

  run_id="$(date +%Y%m%d-%H%M%S)-${issue_id}"
  prompt_file="$LOG_DIR/prompt-$run_id.txt"
  output_file="$LOG_DIR/last-message-$run_id.txt"
  console_log="$LOG_DIR/console-$run_id.log"

  cat > "$prompt_file" <<EOF
Work exactly one bead: $issue_id

Execution contract:
1) Show and claim this bead (set in_progress if not already).
2) Implement and validate to satisfy acceptance criteria.
3) If you hit an easy/trivial fix while implementing, fix inline and continue.
4) If you find a non-trivial/complex bug, do NOT patch blindly:
   - create a dedicated bug bead with reproduction details,
   - make $issue_id depend on that bug bead and set $issue_id to blocked with notes,
   - switch focus to the bug bead and attempt to resolve it first.
5) Leave bead state deterministic at end: closed (done) OR blocked (waiting), never ambiguous.
6) Follow AGENTS.md session-end requirements including sync and push.
EOF

  codex_rc=0
  if [[ -n "$CODEX_SESSION_ID" ]]; then
    if ! codex -C "$ROOT_DIR" exec resume "$CODEX_SESSION_ID" -m "$MODEL" -o "$output_file" - < "$prompt_file" > "$console_log" 2>&1; then
      codex_rc=$?
    fi
  elif [[ "$CODEX_RESUME_LAST" == "1" ]]; then
    if ! codex -C "$ROOT_DIR" exec resume --last -m "$MODEL" -o "$output_file" - < "$prompt_file" > "$console_log" 2>&1; then
      codex_rc=$?
    fi
  else
    if ! codex -C "$ROOT_DIR" -m "$MODEL" -s "$CODEX_SANDBOX" -a "$CODEX_APPROVAL" exec -o "$output_file" - < "$prompt_file" > "$console_log" 2>&1; then
      codex_rc=$?
    fi
  fi

  if [[ "$codex_rc" -eq 0 ]]; then
    status="$(bd show "$issue_id" --json | jq -r '.[0].status')"
    if [[ "$status" == "closed" || "$status" == "blocked" ]]; then
      log "Issue $issue_id ended in status=$status (success)"
      unset 'retries[$issue_id]'
      consecutive_failures=0
    else
      retries[$issue_id]=$((attempts + 1))
      consecutive_failures=$((consecutive_failures + 1))
      log "Issue $issue_id still status=$status; retry ${retries[$issue_id]}/$MAX_RETRIES_PER_ISSUE"
    fi
  else
    retries[$issue_id]=$((attempts + 1))
    consecutive_failures=$((consecutive_failures + 1))
    log "codex run failed for $issue_id (rc=$codex_rc); retry ${retries[$issue_id]}/$MAX_RETRIES_PER_ISSUE"
  fi

  snapshot_after="$(ready_snapshot)"
  if [[ "$snapshot_after" == "$snapshot_before" || "$snapshot_after" == "$last_snapshot" ]]; then
    no_progress_cycles=$((no_progress_cycles + 1))
  else
    no_progress_cycles=0
  fi
  last_snapshot="$snapshot_after"

  if [[ "$consecutive_failures" -ge "$MAX_CONSECUTIVE_FAILURES" ]]; then
    log "Reached $consecutive_failures consecutive failures. Stopping watcher for safety."
    exit 2
  fi

  if [[ "$no_progress_cycles" -ge "$MAX_NO_PROGRESS_CYCLES" ]]; then
    log "Queue made no progress for $no_progress_cycles cycles. Stopping watcher to avoid infinite loop."
    exit 3
  fi

  if [[ "$ONCE" -eq 1 ]]; then
    log "--once set; exiting after one cycle."
    exit 0
  fi

  sleep "$SLEEP_SECONDS"
done

log "Reached MAX_CYCLES=$MAX_CYCLES. Stopping watcher."
exit 4
