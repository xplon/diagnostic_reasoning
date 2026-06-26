from __future__ import annotations

from typing import Any

from diagnostic_reasoning.domains.cbc import CBC_ANALYTES, grade_crossed, grade_report, normalize_report
from diagnostic_reasoning.schema import GradeResult, PatientState, TrendFact

DEFAULT_MISSING_CONTEXT = [
    "fever",
    "bleeding",
    "infection_signs",
    "current_therapy_regimen",
    "days_since_last_therapy",
    "prior_G_CSF_or_platelet_support",
]


def _event_time(event: dict[str, Any], index: int) -> tuple[str, int]:
    return (event.get("t") or event.get("report_time") or "9999-99-99", index)


def ordered_events(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    events = timeline.get("events", [])
    return [event for _, event in sorted(enumerate(events), key=lambda pair: _event_time(pair[1], pair[0]))]


def lab_events_until(
    timeline: dict[str, Any],
    reports_by_id: dict[str, dict[str, Any]],
    target_report_id: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for event in ordered_events(timeline):
        event_type = event.get("event_type") or event.get("type")
        payload = event.get("payload", event)
        report_id = payload.get("report_id") or payload.get("verified_lab_id")
        if event_type in {"lab", "lab_report"} and report_id in reports_by_id:
            selected.append((event, reports_by_id[report_id]))
            if report_id == target_report_id:
                return selected
    if target_report_id in reports_by_id:
        selected.append(({"event_type": "lab", "payload": {"report_id": target_report_id}}, reports_by_id[target_report_id]))
    return selected


def compute_trends(
    timeline: dict[str, Any],
    reports_by_id: dict[str, dict[str, Any]],
    target_report_id: str,
    analytes: tuple[str, ...] = CBC_ANALYTES,
    relative_threshold_pct: float = 40.0,
) -> list[TrendFact]:
    events = lab_events_until(timeline, reports_by_id, target_report_id)
    if not events:
        return []
    current_report = reports_by_id[target_report_id]
    current = normalize_report(current_report)
    trends: list[TrendFact] = []

    for analyte in analytes:
        current_field = current.get("fields", {}).get(analyte)
        if not current_field or current_field.get("value") is None:
            continue

        previous_report = None
        for _, candidate in reversed(events[:-1]):
            field = normalize_report(candidate).get("fields", {}).get(analyte)
            if field and field.get("value") is not None:
                previous_report = candidate
                break
        if previous_report is None:
            continue

        prev_field = normalize_report(previous_report)["fields"][analyte]
        previous_value = float(prev_field["value"])
        current_value = float(current_field["value"])
        if previous_value == 0:
            continue
        delta = current_value - previous_value
        delta_pct = delta / previous_value * 100.0
        direction = "stable"
        if delta > 0:
            direction = "up"
        elif delta < 0:
            direction = "down"

        previous_grade = grade_report(previous_report).get(analyte)
        current_grade = grade_report(current_report).get(analyte)
        crossed = grade_crossed(
            previous_grade.grade if previous_grade else None,
            current_grade.grade if current_grade else None,
        )
        substantial = abs(delta_pct) >= relative_threshold_pct or crossed
        trends.append(
            TrendFact(
                analyte=analyte,
                previous_report_id=previous_report["report_id"],
                current_report_id=current_report["report_id"],
                previous_value=previous_value,
                current_value=current_value,
                delta=round(delta, 4),
                delta_pct=round(delta_pct, 1),
                direction=direction,
                verdict="substantial" if substantial else "minor",
                reason="relative_change_or_grade_boundary" if substantial else "below_threshold",
            )
        )
    return trends


def prior_nadir(
    timeline: dict[str, Any],
    reports_by_id: dict[str, dict[str, Any]],
    target_report_id: str,
    analytes: tuple[str, ...] = CBC_ANALYTES,
) -> dict[str, float]:
    events = lab_events_until(timeline, reports_by_id, target_report_id)
    nadir: dict[str, float] = {}
    for _, report in events:
        normalized = normalize_report(report)
        for analyte in analytes:
            field = normalized.get("fields", {}).get(analyte)
            value = field.get("value") if field else None
            if value is None:
                continue
            nadir[analyte] = min(float(value), nadir.get(analyte, float(value)))
    return nadir


def detect_prior_support(timeline: dict[str, Any], target_report_id: str) -> list[dict[str, Any]]:
    support_events: list[dict[str, Any]] = []
    for event in ordered_events(timeline):
        event_type = event.get("event_type") or event.get("type")
        payload = event.get("payload", event)
        if event_type in {"lab", "lab_report"}:
            report_id = payload.get("report_id") or payload.get("verified_lab_id")
            if report_id == target_report_id:
                break
        if event_type == "support":
            support_events.append(payload)
    return support_events


def derive_state(
    timeline: dict[str, Any],
    reports_by_id: dict[str, dict[str, Any]],
    target_report_id: str,
) -> PatientState:
    report = reports_by_id[target_report_id]
    grades = grade_report(report)
    state = PatientState(
        patient_id=timeline["patient_id"],
        patient_timeline_id=timeline["patient_timeline_id"],
        t_index=report.get("collected_at") or report.get("report_time"),
        latest_report_id=target_report_id,
        latest_grades=grades,
        trends=compute_trends(timeline, reports_by_id, target_report_id),
        prior_nadir=prior_nadir(timeline, reports_by_id, target_report_id),
        prior_support=detect_prior_support(timeline, target_report_id),
        missing_context=list(DEFAULT_MISSING_CONTEXT),
        domain_states={
            "cbc": {
                "report_id": target_report_id,
                "report_domain": report.get("report_domain", "cbc"),
            }
        },
    )
    return state


def state_to_dict(state: PatientState) -> dict[str, Any]:
    return {
        "patient_id": state.patient_id,
        "patient_timeline_id": state.patient_timeline_id,
        "t_index": state.t_index,
        "latest_report_id": state.latest_report_id,
        "latest_grades": {
            key: value.__dict__ if isinstance(value, GradeResult) else value
            for key, value in state.latest_grades.items()
        },
        "trends": [trend.__dict__ for trend in state.trends],
        "prior_nadir": state.prior_nadir,
        "prior_support": state.prior_support,
        "missing_context": state.missing_context,
        "domain_states": state.domain_states,
    }
