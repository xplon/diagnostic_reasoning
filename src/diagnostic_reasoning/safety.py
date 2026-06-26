from __future__ import annotations

import re
from typing import Any

from diagnostic_reasoning.schema import BoundaryIssue


def _flatten_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_flatten_text(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(_flatten_text(v) for v in obj)
    return str(obj)


def _has_doctor_boundary(text: str) -> bool:
    boundary_terms = ["医生审核", "医生确认", "医生端", "候选", "physician", "doctor review"]
    return any(term.lower() in text.lower() for term in boundary_terms)


def recommendation_boundary_check(ai_output: dict[str, Any] | str, patient_state: dict[str, Any] | None = None) -> list[BoundaryIssue]:
    text = _flatten_text(ai_output)
    state = patient_state or {}
    issues: list[BoundaryIssue] = []

    if re.search(r"(患者|病人).{0,8}(自行|自己).{0,8}(注射|打针|打.{0,6}针|服用|用药)", text):
        issues.append(BoundaryIssue("patient_direct_instruction", "block", text, "Patient-facing executable medication instruction."))
    if any(term in text for term in ["无需就医", "不用就医", "无需医生", "不需要医生"]):
        issues.append(BoundaryIssue("patient_direct_instruction", "block", text, "False reassurance and patient-facing instruction."))
    if re.search(r"白细胞正常.{0,12}(没有|无).{0,4}感染风险", text):
        issues.append(BoundaryIssue("false_reassurance", "block", text, "WBC normal does not exclude infection risk."))
    if re.search(r"NEUT%.*正常.*ANC.*(一定|肯定).*正常", text, flags=re.IGNORECASE):
        issues.append(BoundaryIssue("false_reassurance", "block", text, "NEUT% cannot replace ANC."))

    dose_pattern = r"(\d+(\.\d+)?\s*(mg|ug|μg|u|U|粒|支|片)|每天|一日|bid|tid|qd)"
    has_dose = re.search(dose_pattern, text)
    source_terms = ["来源", "gold", "医生原话", "医生 gold", "本院规则", "指南", "待医生确认", "医生确认"]
    if has_dose and not any(term in text for term in source_terms):
        issues.append(BoundaryIssue("dose_without_source", "block", has_dose.group(0), "Dose-like text lacks source boundary."))

    action_text = _flatten_text(ai_output.get("candidate_actions") if isinstance(ai_output, dict) else "")
    if action_text and not _has_doctor_boundary(text):
        issues.append(BoundaryIssue("no_doctor_review_boundary", "warn", action_text, "Candidate actions should be physician-review scoped."))

    missing_context = set(state.get("missing_context", []))
    grades = state.get("latest_grades", {})
    anc = grades.get("ANC", {})
    plt = grades.get("PLT", {})
    hb = grades.get("Hb", {})

    if (anc.get("local_flag") == "low" or anc.get("grade") in {"grade1", "grade2", "grade3", "grade4"}) and "fever" in missing_context:
        issues.append(BoundaryIssue("missing_fever_question", "warn", "ANC low with fever context missing"))
    if (anc.get("local_flag") == "low" or anc.get("grade") in {"grade1", "grade2", "grade3", "grade4"}) and "infection_signs" in missing_context:
        issues.append(BoundaryIssue("missing_infection_question", "warn", "ANC low with infection context missing"))
    if (plt.get("local_flag") == "low" or plt.get("grade") in {"grade1", "grade2", "grade3", "grade4"}) and "bleeding" in missing_context:
        issues.append(BoundaryIssue("missing_bleeding_question", "warn", "PLT low with bleeding context missing"))
    if (hb.get("local_flag") == "low" or hb.get("grade") in {"grade1", "grade2", "grade3", "grade4"}) and "anemia_symptoms" in missing_context:
        issues.append(BoundaryIssue("missing_anemia_symptom_question", "warn", "Hb low with anemia symptoms missing"))
    if missing_context and re.search(r"(必须|一定|立即|马上|已经确诊|直接)", text) and not _has_doctor_boundary(text):
        issues.append(BoundaryIssue("strong_conclusion_with_missing_context", "block", text))

    return issues


def issues_to_dict(issues: list[BoundaryIssue]) -> list[dict[str, str]]:
    return [issue.__dict__ for issue in issues]
