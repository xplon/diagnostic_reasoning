# Doctor Reasoning Reconstruction

This project has two separate reasoning flows:

- `run-case`: predicts baseline candidate actions from structured lab data.
- `reconstruct-case`: uses the doctor's gold statement and gold actions to reconstruct the intermediate reasoning that could explain why the doctor said it.

The reconstruction output always sets `uses_doctor_gold=true`. It is for training, review, rule-candidate discovery, and case memory. It is not a hidden-evaluation prediction.

## CLI

Single case:

```bash
uv run diagnostic-reasoning reconstruct-case ^
  --data-dir fixtures\synthetic_dataset ^
  --case-id case_synth_002
```

Whole dataset:

```bash
uv run diagnostic-reasoning reconstruct-dataset ^
  --data-dir fixtures\synthetic_dataset ^
  --output outputs\synthetic_doctor_reasoning_reconstructions.json
```

## API

- `GET /api/v1/reconstruct/{case_id}`
- `GET /api/v1/reconstruct`

## Output

Each reconstruction includes:

- `doctor_statement`: the doctor's original comment.
- `gold_actions`: the supervised action labels used for reconstruction.
- `supporting_facts`: lab values, local reference status, CTCAE-style grade when available, and evidence role.
- `supporting_trends`: timeline-derived trends relevant to the doctor's target action.
- `doctor_stated_unverified_trends`: trend claims that come from doctor/gold text but need prior-lab verification.
- `exclusions`: why abnormal but non-target findings should not be forced into the doctor's selected action.
- `safety_gaps`: missing context before a physician-reviewed label could become an executable recommendation.
- `scope_notes`: whether the case is inside CBC Phase 1 or preserved out of phase 1.
- `source_boundary`: leakage and prescription-safety metadata.
- `agreement_with_baseline`: how the baseline prediction compares with the doctor gold action, only for CBC-domain cases.

Non-CBC or biochemistry-targeted comments are preserved and marked as `preserved_out_of_phase1`. Medication, injection, and dose text is stored only as case-specific doctor evidence and must not be generalized into patient-facing prescription rules.
