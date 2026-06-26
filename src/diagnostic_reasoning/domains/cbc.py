from __future__ import annotations

from copy import deepcopy
from typing import Any

from diagnostic_reasoning.schema import CandidateAction, GradeResult

CBC_ANALYTES = ("WBC", "ANC", "Hb", "PLT")
GRADE_RANK = {
    "not_decreased": 0,
    "not_anemic_by_local_range": 0,
    "none": 0,
    "grade1": 1,
    "grade2": 2,
    "grade3": 3,
    "grade4": 4,
}


def local_flag(value: float | None, ref: list[float] | None) -> str:
    if value is None:
        return "missing"
    if not ref or len(ref) != 2:
        return "unknown"
    low, high = ref
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "normal"


def normalize_field(analyte: str, field: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(field)
    value = normalized.get("value")
    unit = normalized.get("unit")
    if value is None:
        normalized["flag"] = "missing"
        return normalized

    if analyte == "Hb" and unit in {"g/dL", "gdl", "g per dL"}:
        normalized["value"] = float(value) * 10.0
        normalized["unit"] = "g/L"
        if normalized.get("ref"):
            normalized["ref"] = [float(v) * 10.0 for v in normalized["ref"]]
    elif analyte in {"WBC", "ANC", "ALC", "PLT"}:
        normalized["unit"] = "10^9/L"
        normalized["value"] = float(value)
    elif analyte == "RBC":
        normalized["unit"] = "10^12/L"
        normalized["value"] = float(value)
    elif analyte.endswith("_percent") or unit == "%":
        normalized["unit"] = "%"
        normalized["value"] = float(value)
    else:
        normalized["value"] = float(value)

    normalized["flag"] = local_flag(normalized.get("value"), normalized.get("ref"))
    return normalized


def normalize_report(report: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(report)
    normalized["fields"] = {
        key: normalize_field(key, value)
        for key, value in report.get("fields", {}).items()
    }
    normalized["normalization_status"] = "normalized_v0"
    return normalized


def grade_field(analyte: str, field: dict[str, Any]) -> GradeResult:
    value = field.get("value")
    flag = field.get("flag") or local_flag(value, field.get("ref"))
    unit = field.get("unit")

    if value is None:
        return GradeResult(analyte, "missing", None, unit, flag, rationale="value missing")

    grade = "none"
    rationale = "not graded"

    if analyte == "WBC":
        if value < 1.0:
            grade = "grade4"
        elif value < 2.0:
            grade = "grade3"
        elif value < 3.0:
            grade = "grade2"
        elif flag == "low":
            grade = "grade1"
        else:
            grade = "not_decreased"
    elif analyte == "ANC":
        if value < 0.5:
            grade = "grade4"
        elif value < 1.0:
            grade = "grade3"
        elif value < 1.5:
            grade = "grade2"
        elif flag == "low":
            grade = "grade1"
        else:
            grade = "not_decreased"
    elif analyte == "PLT":
        if value < 25:
            grade = "grade4"
        elif value < 50:
            grade = "grade3"
        elif value < 75:
            grade = "grade2"
        elif flag == "low":
            grade = "grade1"
        else:
            grade = "not_decreased"
    elif analyte == "Hb":
        if value < 80:
            grade = "grade3"
        elif value < 100:
            grade = "grade2"
        elif flag == "low":
            grade = "grade1"
        else:
            grade = "not_anemic_by_local_range"
    else:
        grade = "not_applicable"

    rationale = f"{analyte}={value} {unit}, local_flag={flag}, source=CTCAE v5.0"
    return GradeResult(analyte, grade, value, unit, flag, rationale=rationale)


def grade_report(report: dict[str, Any]) -> dict[str, GradeResult]:
    normalized = normalize_report(report)
    fields = normalized.get("fields", {})
    return {
        analyte: grade_field(analyte, fields[analyte])
        for analyte in CBC_ANALYTES
        if analyte in fields
    }


def grade_crossed(previous_grade: str | None, current_grade: str | None) -> bool:
    return GRADE_RANK.get(previous_grade or "none", 0) != GRADE_RANK.get(current_grade or "none", 0)


def build_fact_atoms(report: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = normalize_report(report)
    atoms: list[dict[str, Any]] = []
    for analyte, field in normalized.get("fields", {}).items():
        if field.get("value") is None:
            continue
        flag = field.get("flag", "unknown")
        vs_ref = {
            "low": "below_local_lower",
            "normal": "within_local",
            "high": "above_local_upper",
        }.get(flag, "unknown")
        atoms.append(
            {
                "type": "fact",
                "analyte": analyte,
                "value": field.get("value"),
                "vs_ref": vs_ref,
                "source": "verified_report",
            }
        )
    return atoms


def recommend_actions(patient_state: dict[str, Any]) -> list[CandidateAction]:
    grades = patient_state.get("latest_grades", {})
    missing_context = patient_state.get("missing_context", [])
    actions: list[CandidateAction] = []

    def grade_for(key: str) -> dict[str, Any]:
        value = grades.get(key, {})
        if isinstance(value, GradeResult):
            return {
                "grade": value.grade,
                "local_flag": value.local_flag,
            }
        return value or {}

    anc = grade_for("ANC")
    plt = grade_for("PLT")
    hb = grade_for("Hb")

    if anc.get("local_flag") == "low" or GRADE_RANK.get(anc.get("grade", "none"), 0) >= 1:
        actions.append(
            CandidateAction(
                "neutrophil_support_review",
                source_rule="anc_low_neutrophil_support_review_v0",
                rationale="ANC is low or CTCAE-graded; review neutrophil support with physician.",
                required_context=["fever", "infection_signs", "days_since_last_therapy", "prior_G_CSF"],
            )
        )
    if plt.get("local_flag") == "low" or GRADE_RANK.get(plt.get("grade", "none"), 0) >= 1:
        actions.append(
            CandidateAction(
                "platelet_support_review",
                source_rule="plt_low_platelet_support_review_v0",
                rationale="PLT is low or CTCAE-graded; review platelet support with physician.",
                required_context=["bleeding", "days_since_last_therapy", "prior_platelet_support"],
            )
        )
    if hb.get("local_flag") == "low" or GRADE_RANK.get(hb.get("grade", "none"), 0) >= 1:
        actions.append(
            CandidateAction(
                "anemia_review",
                source_rule="hb_low_anemia_review_v0",
                rationale="Hb is low or CTCAE-graded; review anemia context with physician.",
                required_context=["anemia_symptoms", "bleeding", "iron_status"],
            )
        )
    if GRADE_RANK.get(hb.get("grade", "none"), 0) >= 3:
        actions.append(
            CandidateAction(
                "transfusion_review",
                source_rule="hb_grade3_transfusion_review_v0",
                rationale="Hb is grade3 or worse; transfusion review is a physician decision.",
                required_context=["anemia_symptoms", "bleeding", "cardiopulmonary_symptoms"],
            )
        )
    if any(GRADE_RANK.get(grade_for(k).get("grade", "none"), 0) >= 3 for k in ("ANC", "PLT")):
        actions.append(
            CandidateAction(
                "dose_modification_review",
                source_rule="severe_cytopenia_dose_modification_review_v0",
                rationale="Severe cytopenia may affect next-cycle treatment decisions.",
                required_context=["current_therapy_regimen", "cycle_number", "days_since_last_therapy"],
            )
        )

    if not actions:
        actions.append(CandidateAction("monitoring_review", rationale="No CBC support target detected."))

    if missing_context:
        actions.append(
            CandidateAction(
                "insufficient_context",
                rationale="Important clinical context is missing.",
                required_context=list(missing_context),
            )
        )
    return actions
