# Repository Instructions

This repository implements physician-reviewed diagnostic-sheet reasoning.

## Core Scope

- The project is not CBC-only. CBC is the first implemented `report_domain`.
- Preserve non-CBC reports in patient timelines even when no domain rules exist yet.
- Treat outputs as physician-facing decision support and evaluation artifacts, not patient instructions.
- Do not generalize doctor case-specific medication or dose text into global rules without owner approval.

## Data Safety

- Never commit raw report images, names, MRNs, sample IDs, real ID mappings, or unredacted private notes.
- Private data belongs outside this repository, typically under `../data_private/`.
- Use `diagnostic-reasoning promote-staging` to create local reviewed data from owner-verified staging files.
- Public tests must use `fixtures/` synthetic or deidentified examples only.

## Gold Leakage

- Do not include `doctor_gold_recommendation`, `gold_actions`, or `gold_reasoning_atoms` in generation prompts unless the task is explicitly review, annotation, evaluation debugging, or owner-supervised learning.
- The Codex context API defaults to `include_gold=false` for this reason.

## Verification

Run before claiming completion:

```bash
python -m pytest
```

For CLI smoke tests without installing the package:

```powershell
$env:PYTHONPATH='src'
python -m diagnostic_reasoning.cli run-case --data-dir fixtures\synthetic_dataset --case-id case_synth_002
python -m diagnostic_reasoning.cli context --data-dir fixtures\synthetic_dataset --case-id case_synth_002 --format markdown
```
