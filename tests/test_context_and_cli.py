from __future__ import annotations

from pathlib import Path

from diagnostic_reasoning.cli import main
from diagnostic_reasoning.context import build_context_bundle, format_context_markdown
from diagnostic_reasoning.io import DataRepository


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_dataset"


def test_context_markdown_excludes_gold_by_default():
    repo = DataRepository(FIXTURE_DIR)
    bundle = build_context_bundle(repo, "case_synth_002")
    md = format_context_markdown(bundle)
    assert "Case Context: case_synth_002" in md
    assert "Doctor Gold" not in md


def test_cli_run_case_smoke():
    rc = main(["run-case", "--data-dir", str(FIXTURE_DIR), "--case-id", "case_synth_002"])
    assert rc == 0
