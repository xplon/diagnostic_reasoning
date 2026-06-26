from __future__ import annotations

import os
from pathlib import Path

from diagnostic_reasoning.context import build_context_bundle, format_context_markdown
from diagnostic_reasoning.io import DataRepository
from diagnostic_reasoning.reasoner import run_case
from diagnostic_reasoning.reconstruction import reconstruct_case, reconstruct_dataset


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_dataset"


def create_app(data_dir: str | None = None):
    try:
        from fastapi import FastAPI, HTTPException, Response
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with: uv sync --extra api") from exc

    app = FastAPI(title="Diagnostic Reasoning Context API", version="0.1.0")
    repo = DataRepository(data_dir or os.getenv("DR_DATA_DIR") or _default_data_dir())

    @app.get("/health")
    def health():
        return {"ok": True, "reports": len(repo.reports), "case_records": len(repo.case_records)}

    @app.get("/api/v1/cases")
    def list_cases():
        return {"case_ids": sorted(repo.cases_by_id)}

    @app.get("/api/v1/cases/{case_id}")
    def get_case(case_id: str, include_gold: bool = False):
        try:
            bundle = build_context_bundle(repo, case_id, include_gold=include_gold)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return bundle

    @app.get("/api/v1/run-case/{case_id}")
    def run_case_endpoint(case_id: str):
        try:
            case = repo.get_case(case_id)
            timeline = repo.get_timeline(case["patient_timeline_id"])
            return run_case(case, timeline, repo.reports_by_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/reconstruct/{case_id}")
    def reconstruct_case_endpoint(case_id: str):
        try:
            case = repo.get_case(case_id)
            timeline = repo.get_timeline(case["patient_timeline_id"])
            return reconstruct_case(case, timeline, repo.reports_by_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/reconstruct")
    def reconstruct_dataset_endpoint():
        return reconstruct_dataset(repo)

    @app.get("/api/v1/codex/context/{case_id}")
    def codex_context(case_id: str, format: str = "json", include_gold: bool = False):
        try:
            bundle = build_context_bundle(repo, case_id, include_gold=include_gold)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if format == "markdown":
            return Response(format_context_markdown(bundle), media_type="text/markdown; charset=utf-8")
        return bundle

    return app


app = create_app()
