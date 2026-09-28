"""Small local operator shell for the persistent demo host."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .runtime import FableRuntime
from .memory_lane import MemoryLane
from .state import assemble_current
from .formation_context import assemble_formation_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Fable demo host runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "record", "inspect", "history", "stage", "correct", "confirm", "memory", "memory-history", "state", "formation-context"):
        command = sub.add_parser(name)
        command.add_argument("vault", type=Path)
        if name == "record":
            command.add_argument("--kind", required=True, choices=("statement", "correction", "decision", "outcome", "observation"))
            command.add_argument("--subject", required=True, choices=("host", "assistant_self", "relationship"))
            command.add_argument("--relates-to")
            command.add_argument("--id", dest="logical_id")
            command.add_argument("--at", dest="occurred_at")
            command.add_argument("--text-file", type=Path, help="Read text from this file; otherwise read stdin")
        if name == "history":
            command.add_argument("--reveal", action="store_true", help="Explicitly show decrypted text")
        if name in {"stage", "correct"}:
            command.add_argument("--id", dest="logical_id", required=True, help="Source observation ID")
            command.add_argument("--key", required=True, help="Explicit host memory key")
            command.add_argument("--category", choices=("profile", "goal", "project"), default="profile")
        if name == "confirm":
            command.add_argument("--candidate", required=True)
            command.add_argument("--target-memory", help="Existing memory ID for a linked correction")
        if name in {"memory", "memory-history"}:
            command.add_argument("--key", required=True)
        if name == "state":
            command.add_argument("--host-key", action="append", default=[], help="One confirmed host key to include")
        if name == "formation-context":
            command.add_argument("--id", dest="logical_id", required=True, help="Source observation ID")
            command.add_argument("--host-key", action="append", default=[], help="Explicit current host key to include")
    args = parser.parse_args()
    if args.command == "init":
        runtime = FableRuntime.initialize(args.vault)
        result = runtime.inspect()
    else:
        runtime = FableRuntime(args.vault)
        if args.command == "record":
            text = args.text_file.read_text() if args.text_file else sys.stdin.read()
            result = runtime.record(kind=args.kind, subject=args.subject, text=text,
                                    relates_to=args.relates_to, logical_id=args.logical_id,
                                    occurred_at=args.occurred_at)
        elif args.command == "inspect":
            result = runtime.inspect()
        elif args.command == "history":
            result = [item.record() if args.reveal else {key: value for key, value in item.record().items() if key != "text"}
                      for item in runtime.history()]
        elif args.command == "stage":
            result = MemoryLane(runtime).stage_host_statement(logical_id=args.logical_id, key=args.key,
                                                               category=args.category)
        elif args.command == "correct":
            result = MemoryLane(runtime).stage_host_correction(logical_id=args.logical_id, key=args.key,
                                                               category=args.category)
        elif args.command == "confirm":
            result = MemoryLane(runtime).confirm(args.candidate, target_memory_id=args.target_memory)
        elif args.command == "memory":
            result = MemoryLane(runtime).current(key=args.key)
        elif args.command == "memory-history":
            result = MemoryLane(runtime).history(key=args.key)
        elif args.command == "state":
            result = assemble_current(runtime, host_keys=tuple(args.host_key))
        else:
            result = assemble_formation_context(runtime, logical_id=args.logical_id,
                                                host_keys=tuple(args.host_key))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
