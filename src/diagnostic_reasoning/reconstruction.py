from __future__ import annotations

import re
from collections import Counter
from typing import Any

from diagnostic_reasoning.domains.cbc import normalize_report
from diagnostic_reasoning.evaluation import score_actions, score_reasoning_atoms
from diagnostic_reasoning.io import DataRepository
from diagnostic_reasoning.reasoner import run_case


CORE_CBC_ANALYTES = ("WBC", "ANC", "NEUT_percent", "Hb", "RBC", "PLT")

ACTION_ANALYTES = {
    "monitoring_review": ("WBC", "ANC", "Hb", "PLT"),
    "neutrophil_support_review": ("WBC", "ANC", "NEUT_percent"),
    "platelet_support_review": ("PLT",),
    "anemia_review": ("Hb", "RBC"),
    "transfusion_review": ("Hb",),
    "dose_modification_review": ("WBC", "ANC", "PLT", "Hb"),
    "urgent_fever_neutropenia_review": ("WBC", "ANC", "NEUT_percent"),
    "urgent_bleeding_thrombocytopenia_review": ("PLT",),
    "hospitalization_or_isolation_review": ("WBC", "ANC", "PLT", "Hb"),
}

ACTION_EXPLANATIONS = {
    "monitoring_review": "doctor judged the available labs as acceptable for monitoring rather than a support intervention",
    "neutrophil_support_review": "doctor targeted low leukocyte or neutrophil-related values for physician-reviewed support",
    "platelet_support_review": "doctor targeted low platelet count for physician-reviewed support",
    "anemia_review": "doctor targeted low hemoglobin or anemia context for review",
    "transfusion_review": "doctor targeted severe anemia or transfusion context for physician review",
    "dose_modification_review": "doctor targeted cytopenia severity that may affect treatment scheduling or dose decisions",
    "urgent_fever_neutropenia_review": "doctor targeted possible febrile neutropenia risk, which requires symptom context",
    "urgent_bleeding_thrombocytopenia_review": "doctor targeted thrombocytopenia with possible bleeding risk",
    "hospitalization_or_isolation_review": "doctor targeted a high-risk state requiring clinician disposition review",
}

ACTION_REQUIRED_CONTEXT = {
    "monitoring_review": ("fever", "bleeding", "current_therapy_regimen", "days_since_last_therapy"),
    "neutrophil_support_review": ("fever", "infection_signs", "days_since_last_therapy", "prior_G_CSF_or_platelet_support"),
    "platelet_support_review": ("bleeding", "days_since_last_therapy", "prior_G_CSF_or_platelet_support"),
    "anemia_review": ("bleeding", "anemia_symptoms"),
    "transfusion_review": ("anemia_symptoms", "bleeding", "cardiopulmonary_symptoms"),
    "dose_modification_review": ("current_therapy_regimen", "cycle_number", "days_since_last_therapy"),
    "urgent_fever_neutropenia_review": ("fever", "infection_signs"),
    "urgent_bleeding_thrombocytopenia_review": ("bleeding",),
    "hospitalization_or_isolation_review": ("fever", "infection_signs", "bleeding", "cardiopulmonary_symptoms"),
}

VS_REF_BY_FLAG = {
    "low": "below_local_lower",
    "normal": "within_local",
    "high": "above_local_upper",
    "missing": "missing",
}

MEDICATION_OR_DOSE_KEYWORDS = (
    "升白针",
    "升血小板",
    "短效",
    "口服",
    "护肝",
    "药",
    "针",
    "每天",
    "每次",
    "粒",
    "片",
    "恒曲",
    "双环醇",
    "易善复",
    "特比澳",
    "特比奥",
    "欣粒生",
    "欣粒升",
)


def _atom_kind(atom: dict[str, Any]) -> str:
    return atom.get("type") or atom.get("atom_type") or ""


def _atom_analyte(atom: dict[str, Any]) -> str | None:
    return atom.get("analyte") or atom.get("field")


def _atom_action(atom: dict[str, Any]) -> str | None:
    return atom.get("action") or atom.get("candidate_action")


def normalize_reasoning_atom(atom: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {"type": _atom_kind(atom)}
    analyte = _atom_analyte(atom)
    action = _atom_action(atom)
    if analyte:
        normalized["analyte"] = analyte
    if action:
        normalized["action"] = action
    for key in (
        "value",
        "unit",
        "flag",
        "vs_ref",
        "direction",
        "verdict",
        "missing",
        "text",
        "source",
        "needs_review",
        "needs_prior_lab",
    ):
        if key in atom:
            normalized[key] = atom[key]
    if normalized.get("flag") and "vs_ref" not in normalized:
        normalized["vs_ref"] = VS_REF_BY_FLAG.get(normalized["flag"], normalized["flag"])
    return normalized


def _is_cbc_target(case_record: dict[str, Any], report: dict[str, Any]) -> bool:
    scope = str(case_record.get("report_scope") or "")
    domain = report.get("report_domain")
    has_cbc_fields = bool(set(report.get("fields", {})) & set(CORE_CBC_ANALYTES))
    return domain == "cbc" or (scope.startswith("cbc") and has_cbc_fields)


def _field_vs_ref(field: dict[str, Any]) -> str:
    flag = field.get("flag", "unknown")
    return VS_REF_BY_FLAG.get(flag, "unknown")


def _field_fact(analyte: str, field: dict[str, Any], grade: dict[str, Any] | None) -> dict[str, Any]:
    fact = {
        "type": "fact",
        "analyte": analyte,
        "value": field.get("value"),
        "unit": field.get("unit"),
        "flag": field.get("flag", "unknown"),
        "vs_ref": _field_vs_ref(field),
        "ref": field.get("ref"),
        "source": "verified_report",
    }
    if grade:
        fact["grade"] = grade.get("grade")
        fact["grading_source"] = grade.get("grading_source")
    if field.get("needs_review"):
        fact["needs_review"] = True
    return fact


def _target_analytes(gold_actions: list[str]) -> set[str]:
    analytes: set[str] = set()
    for action in gold_actions:
        analytes.update(ACTION_ANALYTES.get(action, ()))
    if not analytes or "monitoring_review" in gold_actions:
        analytes.update(ACTION_ANALYTES["monitoring_review"])
    return analytes


def _fact_role(analyte: str, fact: dict[str, Any], gold_actions: list[str], target_analytes: set[str]) -> str:
    flag = fact.get("flag")
    if "monitoring_review" in gold_actions and analyte in target_analytes and flag == "normal":
        return "supports_monitoring"
    if analyte in target_analytes and flag in {"low", "high", "missing"}:
        return "direct_support"
    if flag in {"low", "high", "missing"}:
        return "boundary_or_exclusion_context"
    if analyte in target_analytes:
        return "target_context"
    return "background_context"


def _supporting_facts(
    report: dict[str, Any],
    state: dict[str, Any],
    gold_actions: list[str],
    cbc_target: bool,
) -> list[dict[str, Any]]:
    normalized = normalize_report(report)
    fields = normalized.get("fields", {})
    grades = state.get("latest_grades", {})
    target_analytes = _target_analytes(gold_actions)
    facts: list[dict[str, Any]] = []

    for analyte, field in fields.items():
        if cbc_target and analyte not in CORE_CBC_ANALYTES and field.get("flag") == "normal":
            continue
        fact = _field_fact(analyte, field, grades.get(analyte))
        fact["role"] = _fact_role(analyte, fact, gold_actions, target_analytes)
        if cbc_target:
            if analyte in CORE_CBC_ANALYTES or fact["role"] != "background_context":
                facts.append(fact)
        else:
            facts.append(fact)
    return facts


def _supporting_trends(state: dict[str, Any], gold_actions: list[str]) -> list[dict[str, Any]]:
    target_analytes = _target_analytes(gold_actions)
    trends: list[dict[str, Any]] = []
    for trend in state.get("trends", []):
        analyte = trend.get("analyte")
        if analyte not in target_analytes and trend.get("verdict") != "substantial":
            continue
        item = dict(trend)
        item["source"] = "trend_engine"
        item["role"] = "direct_support" if analyte in target_analytes else "context_substantial_change"
        trends.append(item)
    return trends


def _doctor_stated_unverified_trends(gold_atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trends: list[dict[str, Any]] = []
    for atom in gold_atoms:
        if _atom_kind(atom) != "trend":
            continue
        item = normalize_reasoning_atom(atom)
        item["verification_status"] = (
            "needs_prior_lab" if item.get("needs_prior_lab") else "doctor_stated_or_gold_labeled"
        )
        trends.append(item)
    return trends


def _reconstructed_actions(gold_actions: list[str]) -> list[dict[str, Any]]:
    actions = []
    for action in gold_actions:
        actions.append(
            {
                "action": action,
                "source": "doctor_gold_action",
                "supporting_analytes": list(ACTION_ANALYTES.get(action, ())),
                "explanation": ACTION_EXPLANATIONS.get(action, "doctor gold action preserved for review"),
            }
        )
    return actions


def _baseline_action_names(baseline: dict[str, Any]) -> list[str]:
    names = []
    for action in baseline.get("candidate_actions", []):
        name = action.get("action") if isinstance(action, dict) else str(action)
        if name:
            names.append(name)
    return names


def _make_exclusions(
    facts: list[dict[str, Any]],
    state: dict[str, Any],
    gold_actions: list[str],
    baseline: dict[str, Any],
    cbc_target: bool,
) -> list[dict[str, Any]]:
    exclusions: list[dict[str, Any]] = []
    gold = set(gold_actions)
    fact_by_analyte = {fact.get("analyte"): fact for fact in facts}

    if not cbc_target:
        exclusions.append(
            {
                "type": "exclusion",
                "source": "phase1_scope_boundary",
                "text": "Target report or doctor comment is outside the current CBC action domain; do not force it into CBC support labels.",
            }
        )
        return exclusions

    wbc = fact_by_analyte.get("WBC")
    anc = fact_by_analyte.get("ANC")
    if "monitoring_review" in gold and wbc and anc and wbc.get("flag") == "low" and anc.get("flag") == "normal":
        exclusions.append(
            {
                "type": "exclusion",
                "source": "lab_plus_doctor_gold",
                "text": "WBC is below local reference, but ANC is within local reference and doctor chose monitoring rather than neutrophil support.",
                "analytes": ["WBC", "ANC"],
            }
        )

    for fact in facts:
        analyte = fact.get("analyte")
        if fact.get("flag") not in {"low", "high"}:
            continue
        if analyte in _target_analytes(gold_actions):
            continue
        if "monitoring_review" in gold or gold:
            exclusions.append(
                {
                    "type": "exclusion",
                    "source": "lab_plus_doctor_gold",
                    "text": f"{analyte} is {fact.get('flag')} by local reference, but it is not the doctor's target action in this case.",
                    "analyte": analyte,
                }
            )

    for predicted in _baseline_action_names(baseline):
        if predicted == "insufficient_context" or predicted in gold:
            continue
        exclusions.append(
            {
                "type": "exclusion",
                "source": "baseline_vs_doctor_gold",
                "text": f"Baseline suggested {predicted}, but doctor gold did not select that action; keep this as a review signal, not an automatic rule.",
                "action": predicted,
            }
        )

    anc_grade = state.get("latest_grades", {}).get("ANC", {})
    if anc_grade.get("grade") in {"grade3", "grade4"} and "urgent_fever_neutropenia_review" not in gold:
        exclusions.append(
            {
                "type": "exclusion",
                "source": "safety_boundary",
                "text": "Severe neutropenia alone is not enough to assign urgent fever-neutropenia without fever or infection evidence.",
                "analyte": "ANC",
            }
        )
    return exclusions


def _make_safety_gaps(state: dict[str, Any], gold_actions: list[str], cbc_target: bool) -> list[dict[str, Any]]:
    if not cbc_target:
        return [
            {
                "type": "safety_gap",
                "missing": "non_cbc_reasoning_rules",
                "source": "phase1_scope_boundary",
                "why_it_matters": "Current implementation preserves non-CBC doctor comments but does not yet infer liver, kidney, electrolyte, or medication-adjustment rules.",
            }
        ]

    required: set[str] = set()
    for action in gold_actions or ["monitoring_review"]:
        required.update(ACTION_REQUIRED_CONTEXT.get(action, ()))
    available_missing = set(state.get("missing_context", []))
    gaps = sorted(required | (available_missing & {"fever", "bleeding", "infection_signs"}))
    return [
        {
            "type": "safety_gap",
            "missing": gap,
            "source": "missing_context",
            "why_it_matters": "Needed before turning a physician-reviewed action label into an executable clinical recommendation.",
        }
        for gap in gaps
    ]


def _scope_notes(case_record: dict[str, Any], report: dict[str, Any], cbc_target: bool) -> list[dict[str, Any]]:
    if cbc_target:
        return [
            {
                "scope": "cbc_phase1",
                "status": "implemented",
                "note": "CBC remains the first implemented reasoning domain, not the boundary of the full project.",
            }
        ]
    return [
        {
            "scope": case_record.get("report_scope") or report.get("report_domain") or "unknown",
            "status": "preserved_out_of_phase1",
            "note": "Doctor text is preserved, but no CBC candidate action is inferred for this case.",
        }
    ]


def _detect_medication_or_dose_mentions(text: str | None) -> list[str]:
    if not text:
        return []
    mentions = {keyword for keyword in MEDICATION_OR_DOSE_KEYWORDS if keyword in text}
    mentions.update(re.findall(r"\d+(?:\.\d+)?\s?(?:mg|g|ml|支|针|片|粒|次|天)", text, flags=re.IGNORECASE))
    return sorted(mentions)


def _source_boundary(case_record: dict[str, Any], medication_mentions: list[str]) -> dict[str, Any]:
    return {
        "uses_doctor_gold": True,
        "uses_gold_actions": True,
        "uses_gold_reasoning_atoms_as_alignment_reference": bool(case_record.get("gold_reasoning_atoms")),
        "reconstruction_mode": "deterministic_doctor_gold_reconstruction_v0",
        "hidden_eval_safe": False,
        "prescription_boundary": {
            "has_medication_or_dose_text": bool(medication_mentions),
            "mentions": medication_mentions,
            "rule": "Preserve doctor medication or dose text as case-specific evidence only; do not generalize it into patient-facing prescription instructions.",
        },
    }


def _reasoning_atoms(
    facts: list[dict[str, Any]],
    trends: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    safety_gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    for fact in facts:
        atoms.append(
            {
                "type": "fact",
                "analyte": fact.get("analyte"),
                "value": fact.get("value"),
                "unit": fact.get("unit"),
                "vs_ref": fact.get("vs_ref"),
                "flag": fact.get("flag"),
                "source": fact.get("source"),
                "role": fact.get("role"),
            }
        )
    for trend in trends:
        atoms.append(
            {
                "type": "trend",
                "analyte": trend.get("analyte"),
                "from": trend.get("previous_value"),
                "to": trend.get("current_value"),
                "direction": trend.get("direction"),
                "verdict": trend.get("verdict"),
                "source": trend.get("source"),
                "role": trend.get("role"),
            }
        )
    for action in actions:
        atoms.append(
            {
                "type": "intervention_target",
                "action": action.get("action"),
                "source": action.get("source"),
                "text": action.get("explanation"),
            }
        )
    atoms.extend(exclusions)
    atoms.extend(safety_gaps)
    return atoms


def reconstruct_case(
    case_record: dict[str, Any],
    timeline: dict[str, Any],
    reports_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    target_report = reports_by_id[case_record["target_report_id"]]
    baseline = run_case(case_record, timeline, reports_by_id)
    state = baseline["patient_state"]
    gold_actions = list(case_record.get("gold_actions", []))
    gold_atoms = [normalize_reasoning_atom(atom) for atom in case_record.get("gold_reasoning_atoms", [])]
    cbc_target = _is_cbc_target(case_record, target_report)

    facts = _supporting_facts(target_report, state, gold_actions, cbc_target)
    trends = _supporting_trends(state, gold_actions) if cbc_target else []
    doctor_stated_trends = _doctor_stated_unverified_trends(case_record.get("gold_reasoning_atoms", []))
    actions = _reconstructed_actions(gold_actions)
    exclusions = _make_exclusions(facts, state, gold_actions, baseline, cbc_target)
    safety_gaps = _make_safety_gaps(state, gold_actions, cbc_target)
    atoms = _reasoning_atoms(facts, trends, actions, exclusions, safety_gaps)
    medication_mentions = _detect_medication_or_dose_mentions(case_record.get("doctor_gold_recommendation"))

    action_alignment = None
    if cbc_target:
        action_alignment = score_actions(baseline.get("candidate_actions", []), gold_actions, baseline.get("safety_violations", []))

    atom_alignment = None
    if gold_atoms:
        atom_alignment = score_reasoning_atoms(atoms, gold_atoms)

    return {
        "case_id": case_record["case_id"],
        "patient_id": case_record.get("patient_id"),
        "patient_timeline_id": case_record.get("patient_timeline_id"),
        "target_report_id": case_record.get("target_report_id"),
        "report_domain": target_report.get("report_domain"),
        "report_scope": case_record.get("report_scope"),
        "evaluation_eligible": case_record.get("evaluation_eligible", True),
        "uses_doctor_gold": True,
        "doctor_statement": case_record.get("doctor_gold_recommendation"),
        "gold_actions": gold_actions,
        "reconstructed_actions": actions,
        "supporting_facts": facts,
        "supporting_trends": trends,
        "doctor_stated_unverified_trends": doctor_stated_trends,
        "exclusions": exclusions,
        "safety_gaps": safety_gaps,
        "scope_notes": _scope_notes(case_record, target_report, cbc_target),
        "source_boundary": _source_boundary(case_record, medication_mentions),
        "baseline_candidate_actions": baseline.get("candidate_actions", []),
        "agreement_with_baseline": action_alignment,
        "gold_atom_alignment": atom_alignment,
        "gold_reasoning_atoms_normalized": gold_atoms,
        "reasoning_atoms": atoms,
    }


def reconstruct_dataset(repo: DataRepository) -> dict[str, Any]:
    reconstructions = []
    for case in repo.case_records:
        timeline = repo.get_timeline(case["patient_timeline_id"])
        reconstructions.append(reconstruct_case(case, timeline, repo.reports_by_id))

    action_labels = Counter(
        reconstruction["agreement_with_baseline"]["label"]
        for reconstruction in reconstructions
        if reconstruction.get("agreement_with_baseline")
    )
    return {
        "summary": {
            "num_cases": len(reconstructions),
            "num_evaluation_eligible": sum(1 for item in reconstructions if item.get("evaluation_eligible")),
            "num_cbc_phase1_or_related": sum(
                1
                for item in reconstructions
                if item.get("agreement_with_baseline") is not None
            ),
            "num_out_of_phase1": sum(
                1
                for item in reconstructions
                if item.get("agreement_with_baseline") is None
            ),
            "baseline_alignment_labels": dict(sorted(action_labels.items())),
            "uses_doctor_gold": True,
            "reconstruction_mode": "deterministic_doctor_gold_reconstruction_v0",
        },
        "reconstructions": reconstructions,
    }
