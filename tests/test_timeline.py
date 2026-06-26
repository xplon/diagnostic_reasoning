from __future__ import annotations

from pathlib import Path

from diagnostic_reasoning.io import DataRepository
from diagnostic_reasoning.timeline import compute_trends, derive_state, state_to_dict


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_dataset"


def test_plt_206_to_60_is_substantial():
    repo = DataRepository(FIXTURE_DIR)
    timeline = repo.get_timeline("ptl_synth_001")
    trends = compute_trends(timeline, repo.reports_by_id, "report_synth_002")
    plt = next(t for t in trends if t.analyte == "PLT")
    assert plt.previous_value == 206
    assert plt.current_value == 60
    assert plt.delta_pct == -70.9
    assert plt.direction == "down"
    assert plt.verdict == "substantial"


def test_anc_4_77_to_1_55_is_substantial():
    repo = DataRepository(FIXTURE_DIR)
    timeline = repo.get_timeline("ptl_synth_001")
    trends = compute_trends(timeline, repo.reports_by_id, "report_synth_002")
    anc = next(t for t in trends if t.analyte == "ANC")
    assert anc.delta_pct == -67.5
    assert anc.verdict == "substantial"


def test_no_previous_lab_returns_empty_trends():
    repo = DataRepository(FIXTURE_DIR)
    timeline = repo.get_timeline("ptl_synth_002")
    assert compute_trends(timeline, repo.reports_by_id, "report_synth_003") == []


def test_derive_state_has_grades_and_missing_context():
    repo = DataRepository(FIXTURE_DIR)
    timeline = repo.get_timeline("ptl_synth_001")
    state = state_to_dict(derive_state(timeline, repo.reports_by_id, "report_synth_002"))
    assert state["latest_grades"]["ANC"]["grade"] == "grade1"
    assert state["latest_grades"]["PLT"]["grade"] == "grade2"
    assert "fever" in state["missing_context"]
