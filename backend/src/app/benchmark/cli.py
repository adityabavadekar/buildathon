"""Benchmark CLI, via ``make benchmark``. Unlike the HTTP route it writes a report
by default, since producing a citable one is the reason to run it here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.benchmark.dataset import DEFAULT_BENCHMARK_SEED, DEFAULT_BENCHMARK_SIZE
from app.benchmark.report import write_report
from app.benchmark.runner import run_benchmark


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="benchmark",
        description="Replay the fixed benchmark dataset and score it against the "
        "holdout arm.",
    )
    parser.add_argument("--size", type=int, default=DEFAULT_BENCHMARK_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_BENCHMARK_SEED)
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Route planning through the LLM instead of deterministic rules.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Score the run without writing a Markdown report.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full run payload as JSON instead of a summary.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark, print a summary, and write a report unless told not to."""
    args = _parse_args(argv)
    run = asyncio.run(
        run_benchmark(size=args.size, seed=args.seed, use_llm=args.use_llm)
    )
    payload = run.as_dict()

    if not args.no_report:
        payload["report_path"] = str(write_report(run))

    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0

    treatment = run.treatment
    holdout = run.holdout
    lines = [
        (
            f"dataset      {payload['dataset']['dataset_version']} "
            f"seed={run.seed} events={payload['dataset']['event_count']}"
        ),
        (
            f"treatment    {treatment.case_count} cases, "
            f"{treatment.recovered_count} recovered "
            f"({treatment.recovery_rate_pct}%)"
        ),
        (
            f"holdout      {holdout.case_count} cases, "
            f"{holdout.recovered_count} recovered "
            f"({holdout.recovery_rate_pct}%)"
        ),
        f"lift         {run.lift_pct_points} percentage points",
        f"coverage     {run.counterfactual_coverage_pct}% of treatment value",
    ]
    if run.is_attribution_reliable:
        lines.append(f"attributable INR {run.attributable_recovered_paise / 100:,.2f}")
    else:
        lines.append("attributable not quoted - control strata too small at this size")
    if run.replay_failures_count:
        lines.append(f"FAILURES     {run.replay_failures_count} events not processed")
    if "report_path" in payload:
        lines.append(f"report       {payload['report_path']}")

    sys.stdout.write("\n".join(lines) + "\n")
    # A run whose events did not all replay cannot support a published figure.
    return 1 if run.replay_failures_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
