from __future__ import annotations

import argparse
import json
from pathlib import Path

from .context import prepare
from .evaluate import evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Fable demo memory experiment")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--evidence-limit", type=int, default=1)
    parser.add_argument("--at", help="Prepare an evidence packet at this ISO timestamp")
    parser.add_argument("--topic", help="Known topic key for evidence packet")
    parser.add_argument("--question", help="Question for evidence packet")
    args = parser.parse_args()
    if args.at or args.topic or args.question:
        if not all((args.at, args.topic, args.question)):
            parser.error("--at, --topic and --question must be supplied together")
        output = prepare(args.fixture, at=args.at, topic=args.topic, question=args.question)
    else:
        output = evaluate(args.fixture, args.evidence_limit)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
