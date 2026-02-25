#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.replay_handoff import ReplayHandoffError, replay_handoff_run, replay_outcome_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay a watcher run artifact deterministically.")
    parser.add_argument("--run-file", required=True, help="Path to run artifact JSONL file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Required: replay without side effects",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.dry_run:
        parser.error("--dry-run is required")

    try:
        outcome = replay_handoff_run(run_file=args.run_file, dry_run=True)
    except ReplayHandoffError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(replay_outcome_json(outcome))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
