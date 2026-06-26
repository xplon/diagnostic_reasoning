# Codex Context API

This project intentionally separates deterministic reasoning from AI usage.

The deterministic core owns:

- schema validation
- report normalization
- CTCAE grading
- timeline trend derivation
- baseline candidate actions
- safety boundary checks
- evaluation metrics

External AI tools such as Codex should request context through a stable read-only boundary instead of scraping files ad hoc.

## CLI Interface

```bash
diagnostic-reasoning context \
  --data-dir fixtures/synthetic_dataset \
  --case-id case_synth_002 \
  --format markdown
```

By default this does not include doctor gold labels. Use `--include-gold` only for review, error analysis, or owner-supervised dataset work.

## HTTP Interface

```bash
uv run uvicorn diagnostic_reasoning.server:app --reload
```

Endpoints:

- `GET /health`
- `GET /api/v1/cases`
- `GET /api/v1/cases/{case_id}?include_gold=false`
- `GET /api/v1/run-case/{case_id}`
- `GET /api/v1/reconstruct/{case_id}`
- `GET /api/v1/reconstruct`
- `GET /api/v1/codex/context/{case_id}?format=markdown&include_gold=false`

## Leakage Rule

For generation/evaluation prompts, `include_gold=false` is the default. Gold labels are available only when the task is explicitly review, debugging, annotation, or owner-supervised learning.

The `reconstruct` endpoints intentionally use doctor gold statements and gold actions. Treat them as training/review endpoints, not hidden-evaluation prediction endpoints. See `docs/doctor_reasoning_reconstruction.md` for the output contract.
