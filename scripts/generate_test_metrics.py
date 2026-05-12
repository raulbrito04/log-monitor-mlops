#!/usr/bin/env python3
"""Update the runtime ML F1 metric used by the monitoring stack."""

from __future__ import annotations

import argparse
import json
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update the runtime ML F1 metric via the Flask monitoring endpoint."
    )
    parser.add_argument("--f1", type=float, default=0.783, help="F1 value to publish.")
    parser.add_argument("--model", default="hybrid_ensemble", help="Model name.")
    parser.add_argument("--dataset", default="holdout", help="Dataset name.")
    parser.add_argument(
        "--url",
        default="http://localhost:5001/metrics/ml_quality",
        help="Flask monitoring endpoint.",
    )
    args = parser.parse_args()

    payload = json.dumps(
        {
            "ml_f1_score": args.f1,
            "model": args.model,
            "dataset": args.dataset,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        args.url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        print(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
