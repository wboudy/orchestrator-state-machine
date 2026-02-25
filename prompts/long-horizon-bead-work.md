You are executing long-horizon bead work in `{{ROOT_DIR}}`.

Target bead for this cycle: `{{ISSUE_ID}}`

Primary objective:
- Reduce the open-bead queue to zero over repeated cycles without sacrificing correctness, traceability, or deterministic state transitions.

Hard execution rules:
1. Work exactly one primary bead for this cycle: `{{ISSUE_ID}}`.
2. Claim it if needed (`bd update {{ISSUE_ID}} --status in_progress`).
3. Read acceptance criteria and dependencies before coding.
4. Implement and validate the intended behavior with tests/checks relevant to touched files.
5. End this bead in exactly one deterministic state:
   - `closed` when acceptance criteria are met, or
   - `blocked` with explicit notes and linked blocker bead.
6. Follow `AGENTS.md` session-close requirements (`git pull --rebase`, `bd sync`, `git push`, verify clean status).

Complex blocker protocol (mandatory):
- If issue is trivial/localized, fix inline and continue.
- If issue is complex, high-risk, or unclear:
  1. Create a dedicated bug bead (`--type bug` if available, otherwise `--type task` with `bug` label).
  2. Include concrete repro steps, observed/expected behavior, scope, and evidence paths.
  3. Link dependency so `{{ISSUE_ID}}` depends on the new bug bead (`bd dep add {{ISSUE_ID}} <bug-id>`).
  4. Mark `{{ISSUE_ID}}` as `blocked` with notes pointing to `<bug-id>`.
  5. Switch focus to the bug bead immediately and attempt resolution.

Return-to-origin rule:
- After closing or decisively blocking the bug bead, re-open the original workflow by setting the next executable bead to `in_progress` and continue queue progression on the next cycle.

Quality bar:
- Prefer small, verifiable commits.
- Do not leave ambiguous status.
- Do not bypass failed checks silently.
