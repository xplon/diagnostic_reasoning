from __future__ import annotations

from copy import deepcopy
from typing import Any

from diagnostic_reasoning.io import DataRepository
from diagnostic_reasoning.reasoner import run_case


def build_context_bundle(
    repo: DataRepository,
    case_id: str,
    include_gold: bool = False,
    include_private_refs: bool = False,
) -> dict[str, Any]:
    case = repo.get_case(case_id)
    timeline = repo.get_timeline(case["patient_timeline_id"])
    target_report = deepcopy(repo.get_report(case["target_report_id"]))
    report_ids = {
        (event.get("payload", event).get("report_id") or event.get("payload", event).get("verified_lab_id"))
        for event in timeline.get("events", [])
    }
    reports = [deepcopy(repo.reports_by_id[rid]) for rid in report_ids if rid in repo.reports_by_id]
    ai_baseline = run_case(case, timeline, repo.reports_by_id)

    safe_case = {
        k: v
        for k, v in case.items()
        if include_gold or k not in {"doctor_gold_recommendation", "gold_actions", "gold_reasoning_atoms"}
    }
    if not include_private_refs:
        for report in reports + [target_report]:
            source = report.get("source", {})
            source.pop("private_image_ref", None)
            source.pop("image_path", None)

    return {
        "case": safe_case,
        "target_report": target_report,
        "timeline": timeline,
        "related_reports": reports,
        "derived_baseline": ai_baseline,
        "gold_included": include_gold,
    }


def format_context_markdown(bundle: dict[str, Any]) -> str:
    case = bundle["case"]
    report = bundle["target_report"]
    baseline = bundle["derived_baseline"]
    lines = [
        f"# Case Context: {case['case_id']}",
        "",
        "## Scope",
        f"- report_domain: {report.get('report_domain')}",
        f"- evaluation_eligible: {case.get('evaluation_eligible')}",
        f"- gold_included: {bundle.get('gold_included')}",
        "",
        "## Target Report",
        f"- report_id: {report.get('report_id')}",
        f"- collected_at: {report.get('collected_at')}",
        "",
        "## Fields",
    ]
    for key, field in report.get("fields", {}).items():
        lines.append(f"- {key}: {field.get('value')} {field.get('unit')} flag={field.get('flag')} ref={field.get('ref')}")
    lines.extend(["", "## Derived Patient State"])
    state = baseline["patient_state"]
    lines.append(f"- missing_context: {', '.join(state.get('missing_context', []))}")
    for key, grade in state.get("latest_grades", {}).items():
        lines.append(f"- grade {key}: {grade.get('grade')} local_flag={grade.get('local_flag')}")
    lines.extend(["", "## Trends"])
    for trend in state.get("trends", []):
        lines.append(
            f"- {trend['analyte']}: {trend['previous_value']} -> {trend['current_value']} "
            f"({trend['delta_pct']}%), {trend['direction']}, {trend['verdict']}"
        )
    lines.extend(["", "## Baseline Candidate Actions"])
    for action in baseline.get("candidate_actions", []):
        lines.append(f"- {action.get('action')}: {action.get('rationale')}")
    if bundle.get("gold_included"):
        lines.extend(["", "## Doctor Gold"])
        lines.append(f"- recommendation: {case.get('doctor_gold_recommendation')}")
        lines.append(f"- gold_actions: {', '.join(case.get('gold_actions', []))}")
    return "\n".join(lines) + "\n"
