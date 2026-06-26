from __future__ import annotations

from diagnostic_reasoning.domains.cbc import build_fact_atoms, recommend_actions
from diagnostic_reasoning.schema import CandidateAction
from diagnostic_reasoning.timeline import state_to_dict


def run_case(
    case_record: dict,
    timeline: dict,
    reports_by_id: dict[str, dict],
) -> dict:
    target_report_id = case_record["target_report_id"]
    from diagnostic_reasoning.timeline import derive_state

    state = derive_state(timeline, reports_by_id, target_report_id)
    state_dict = state_to_dict(state)
    actions = recommend_actions(state_dict)
    report = reports_by_id[target_report_id]
    atoms = build_fact_atoms(report)
    for trend in state.trends:
        atoms.append(
            {
                "type": "trend",
                "analyte": trend.analyte,
                "from": trend.previous_value,
                "to": trend.current_value,
                "direction": trend.direction,
                "verdict": trend.verdict,
                "source": "trend_engine",
            }
        )
    for action in actions:
        if action.action in {"insufficient_context", "monitoring_review"}:
            continue
        atoms.append(
            {
                "type": "intervention_target",
                "action": action.action,
                "source": action.source_rule,
            }
        )
    for missing in state.missing_context:
        atoms.append({"type": "safety_gap", "missing": missing, "source": "missing_context"})

    return {
        "case_id": case_record["case_id"],
        "patient_state": state_dict,
        "candidate_actions": [action.__dict__ if isinstance(action, CandidateAction) else action for action in actions],
        "reasoning_atoms": atoms,
        "missing_context": state.missing_context,
        "safety_violations": [],
        "evidence": [],
    }
