from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

CBC_DOMAIN = "cbc"
REPORT_DOMAINS = {
    "cbc",
    "biochemistry",
    "liver_function",
    "renal_function",
    "electrolytes",
    "coagulation",
    "inflammation",
    "tumor_marker",
    "unknown",
}

CANDIDATE_ACTIONS = {
    "monitoring_review",
    "neutrophil_support_review",
    "platelet_support_review",
    "anemia_review",
    "transfusion_review",
    "dose_modification_review",
    "urgent_fever_neutropenia_review",
    "urgent_bleeding_thrombocytopenia_review",
    "hospitalization_or_isolation_review",
    "insufficient_context",
}

REASONING_ATOM_TYPES = {
    "fact",
    "trend",
    "context",
    "intervention_target",
    "exclusion",
    "safety_gap",
}


@dataclass
class LabField:
    value: float | None
    unit: str
    ref: list[float] | None = None
    ref_source: str = "report"
    flag: str = "unknown"
    confidence: float = 1.0
    needs_review: bool = False
    source_text: str | None = None


@dataclass
class ReportSource:
    report_type: str = "unknown"
    ocr_method: str = "manual"
    human_verified: bool = False
    image_ref: str | None = None
    private_image_ref: str | None = None
    source_markdown: str | None = None
    extraction_status: str | None = None


@dataclass
class VerifiedReport:
    report_id: str
    patient_id: str
    patient_timeline_id: str
    report_domain: str
    report_type: str
    collected_at: str | None
    sample_time: str | None
    source: ReportSource
    fields: dict[str, LabField] = field(default_factory=dict)
    doctor_comment_verbatim: str | None = None
    report_notes: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimelineEvent:
    event_id: str
    event_type: str
    t: str | None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class PatientTimeline:
    patient_timeline_id: str
    patient_id: str
    events: list[TimelineEvent]
    baseline: dict[str, Any] = field(default_factory=dict)
    grouping: dict[str, Any] = field(default_factory=dict)


@dataclass
class GradeResult:
    analyte: str
    grade: str
    value: float | None
    unit: str | None
    local_flag: str = "unknown"
    grading_source: str = "CTCAE v5.0"
    rationale: str | None = None


@dataclass
class TrendFact:
    analyte: str
    previous_report_id: str
    current_report_id: str
    previous_value: float
    current_value: float
    delta: float
    delta_pct: float
    direction: str
    verdict: str
    reason: str


@dataclass
class PatientState:
    patient_id: str
    patient_timeline_id: str
    t_index: str | None
    latest_report_id: str | None
    latest_grades: dict[str, GradeResult] = field(default_factory=dict)
    trends: list[TrendFact] = field(default_factory=list)
    prior_nadir: dict[str, float] = field(default_factory=dict)
    prior_support: list[dict[str, Any]] = field(default_factory=list)
    missing_context: list[str] = field(default_factory=list)
    domain_states: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateAction:
    action: str
    domain: str = CBC_DOMAIN
    source_rule: str | None = None
    rationale: str | None = None
    required_context: list[str] = field(default_factory=list)


@dataclass
class ReasoningAtom:
    atom_type: str
    analyte: str | None = None
    value: float | None = None
    vs_ref: str | None = None
    direction: str | None = None
    verdict: str | None = None
    action: str | None = None
    missing: str | None = None
    text: str | None = None
    source: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BoundaryIssue:
    kind: str
    severity: str
    evidence: str
    detail: str | None = None


@dataclass
class CaseRecord:
    case_id: str
    patient_id: str
    patient_timeline_id: str
    target_report_id: str
    evaluation_eligible: bool = True
    report_scope: str = CBC_DOMAIN
    split: str = "development"
    doctor_gold_recommendation: str | None = None
    gold_actions: list[str] = field(default_factory=list)
    gold_reasoning_atoms: list[dict[str, Any]] = field(default_factory=list)
    ai_output: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def to_plain(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: to_plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_plain(v) for v in obj]
    return obj


def clean_none(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: clean_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [clean_none(v) for v in obj]
    return obj
