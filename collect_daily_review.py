import argparse
import sys
from datetime import date

from src.domain.market_data import GateStatus
from src.services.market_pipeline import build_pipeline


EXIT_CODES = {
    GateStatus.PASSED: 0,
    GateStatus.DRAFT_ONLY: 2,
    GateStatus.FAILED: 3,
}


def main(argv: list[str] | None = None, *, pipeline_factory=build_pipeline) -> int:
    parser = argparse.ArgumentParser(description="Collect audited real A-share daily review data.")
    parser.add_argument("--date", required=True, help="Target trade date, for example 2026-09-01")
    parser.add_argument("--mode", choices=["close", "intraday"], default="close")
    args = parser.parse_args(argv)

    try:
        pipeline = pipeline_factory()
        result = pipeline.collect(date.fromisoformat(args.date), mode=args.mode)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    failed = [check.name for check in result.gate.checks if not check.passed]
    print(f"batch_ids={','.join(str(item) for item in result.batch_ids)}")
    print(f"gate_status={result.gate.status.value}")
    print(f"missing_checks={','.join(failed) if failed else 'none'}")
    if result.fallbacks:
        print(
            "fallbacks="
            + ";".join(
                f"{item.primary_source}->{item.fallback_source}:{item.dataset}"
                for item in result.fallbacks
            )
        )
    return EXIT_CODES[result.gate.status]


if __name__ == "__main__":
    sys.exit(main())
