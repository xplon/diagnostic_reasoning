# Schema Spec v0.1

This is the first executable schema for the new repository.

## Report Domain

`report_domain` is a broad diagnostic-sheet category.

Current values:

- `cbc`
- `biochemistry`
- `liver_function`
- `renal_function`
- `electrolytes`
- `coagulation`
- `inflammation`
- `tumor_marker`
- `unknown`

CBC is the first reasoning domain. Non-CBC reports must be preserved in timelines, even when they are not yet fully rule-scored.

## Core Objects

`VerifiedReport`

- one checked diagnostic report
- contains `report_domain`, source metadata, report time, fields, and provenance
- replaces the old CBC-only mental model, while remaining compatible with `VerifiedLab`

`PatientTimeline`

- one deidentified patient timeline
- contains lab, therapy, support, symptom, and doctor-feedback events
- trend logic must only read events up to the target report

`CaseRecord`

- one reasoning/evaluation task
- points to a timeline and a target report
- may include doctor gold labels when used for evaluation

`ReasoningAtom`

- structured unit for scoring reasoning
- supported types: `fact`, `trend`, `context`, `intervention_target`, `exclusion`, `safety_gap`

`CandidateAction`

- doctor-review candidate action
- first CBC action set:
  - `monitoring_review`
  - `neutrophil_support_review`
  - `platelet_support_review`
  - `anemia_review`
  - `transfusion_review`
  - `dose_modification_review`
  - `urgent_fever_neutropenia_review`
  - `urgent_bleeding_thrombocytopenia_review`
  - `hospitalization_or_isolation_review`
  - `insufficient_context`
