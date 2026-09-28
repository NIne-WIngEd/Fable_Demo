"""Regenerate the checked-in packet manifest through the actual A.L.I.C.E. path."""

from pathlib import Path
import json

from fable_demo.trials import freeze


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    target = root / "fixtures" / "frozen_trials_v1.json"
    target.write_text(json.dumps(freeze(root / "fixtures" / "trials_v1.json"), indent=2) + "\n")
