from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluate import evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Fable demo memory experiment")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--evidence-limit", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.fixture, args.evidence_limit), indent=2))


if __name__ == "__main__":
    main()
