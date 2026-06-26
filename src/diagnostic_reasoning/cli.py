from __future__ import annotations

import argparse
import sys
from pathlib import Path

from diagnostic_reasoning.context import build_context_bundle, format_context_markdown
from diagnostic_reasoning.evaluation import evaluate_dataset
from diagnostic_reasoning.io import DataRepository, write_json
from diagnostic_reasoning.reasoner import run_case
from diagnostic_reasoning.reconstruction import reconstruct_case, reconstruct_dataset
from diagnostic_reasoning.staging_import import promote_staging


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_dataset"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diagnostic-reasoning")
    sub = parser.add_subparsers(dest="command", required=True)

    promote = sub.add_parser("promote-staging")
    promote.add_argument("--staging-dir", required=True)
    promote.add_argument("--output-dir", required=True)
    promote.add_argument("--mark-verified", action="store_true")
    promote.add_argument("--keep-private-image-paths", action="store_true")

    run = sub.add_parser("run-case")
    run.add_argument("--data-dir", default=str(_default_data_dir()))
    run.add_argument("--case-id", required=True)
    run.add_argument("--output")

    context = sub.add_parser("context")
    context.add_argument("--data-dir", default=str(_default_data_dir()))
    context.add_argument("--case-id", required=True)
    context.add_argument("--format", choices=["json", "markdown"], default="json")
    context.add_argument("--include-gold", action="store_true")
    context.add_argument("--include-private-refs", action="store_true")
    context.add_argument("--output")

    eval_cmd = sub.add_parser("eval")
    eval_cmd.add_argument("--data-dir", default=str(_default_data_dir()))
    eval_cmd.add_argument("--output")

    reconstruct = sub.add_parser("reconstruct-case")
    reconstruct.add_argument("--data-dir", default=str(_default_data_dir()))
    reconstruct.add_argument("--case-id", required=True)
    reconstruct.add_argument("--output")

    reconstruct_all = sub.add_parser("reconstruct-dataset")
    reconstruct_all.add_argument("--data-dir", default=str(_default_data_dir()))
    reconstruct_all.add_argument("--output")

    args = parser.parse_args(argv)
    if args.command == "promote-staging":
        summary = promote_staging(
            args.staging_dir,
            args.output_dir,
            mark_verified=args.mark_verified,
            strip_private_image_paths=not args.keep_private_image_paths,
        )
        write_json(Path(args.output_dir) / "dataset_summary.json", summary)
        print(f"Promoted staging dataset to {args.output_dir}")
        print(summary)
        return 0

    if args.command == "run-case":
        repo = DataRepository(args.data_dir)
        case = repo.get_case(args.case_id)
        timeline = repo.get_timeline(case["patient_timeline_id"])
        result = run_case(case, timeline, repo.reports_by_id)
        if args.output:
            write_json(args.output, result)
        else:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "context":
        repo = DataRepository(args.data_dir)
        bundle = build_context_bundle(repo, args.case_id, include_gold=args.include_gold, include_private_refs=args.include_private_refs)
        if args.format == "markdown":
            payload = format_context_markdown(bundle)
            if args.output:
                Path(args.output).write_text(payload, encoding="utf-8")
            else:
                print(payload)
        else:
            if args.output:
                write_json(args.output, bundle)
            else:
                import json

                print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0

    if args.command == "eval":
        repo = DataRepository(args.data_dir)
        outputs = {}
        for case in repo.case_records:
            timeline = repo.get_timeline(case["patient_timeline_id"])
            outputs[case["case_id"]] = run_case(case, timeline, repo.reports_by_id)
        result = evaluate_dataset(repo.case_records, outputs)
        if args.output:
            write_json(args.output, result)
        else:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "reconstruct-case":
        repo = DataRepository(args.data_dir)
        case = repo.get_case(args.case_id)
        timeline = repo.get_timeline(case["patient_timeline_id"])
        result = reconstruct_case(case, timeline, repo.reports_by_id)
        if args.output:
            write_json(args.output, result)
        else:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "reconstruct-dataset":
        repo = DataRepository(args.data_dir)
        result = reconstruct_dataset(repo)
        if args.output:
            write_json(args.output, result)
        else:
            import json

            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
