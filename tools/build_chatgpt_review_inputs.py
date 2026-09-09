"""Replay existing archived objective inputs; never acquire data or import a review."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.formal_review.objective_inputs import build_inputs  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    packet = build_inputs(ROOT, args.date)
    print(
        json.dumps(
            dict(
                date=args.date,
                schema_version=packet["meta"]["schema_version"],
                full_path=f"data/chatgpt_review_inputs/{args.date}.json",
                compact_path=f"data/chatgpt_review_inputs/{args.date}_compact.json",
                data_gap_count=len(packet["data_gaps"]),
            )
        )
    )


if __name__ == "__main__":
    main()
