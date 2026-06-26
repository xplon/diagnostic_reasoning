from __future__ import annotations

from pathlib import Path

import pytest

from diagnostic_reasoning.io import DataRepository
from diagnostic_reasoning.reconstruction import reconstruct_case, reconstruct_dataset


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_dataset"
PRIVATE_REVIEWED_DIR = Path(__file__).resolve().parents[2] / "data_private" / "diagnostic_reasoning" / "reviewed_v0"


def test_reconstruct_case_explains_doctor_gold_actions():
    repo = DataRepository(FIXTURE_DIR)
    case = repo.get_case("case_synth_002")
    timeline = repo.get_timeline(case["patient_timeline_id"])
    result = reconstruct_case(case, timeline, repo.reports_by_id)

    assert result["uses_doctor_gold"] is True
    assert result["gold_actions"] == ["neutrophil_support_review", "platelet_support_review"]
    assert result["agreement_with_baseline"]["label"] == "exact"

    facts = {fact["analyte"]: fact for fact in result["supporting_facts"]}
    assert facts["WBC"]["vs_ref"] == "within_local"
    assert facts["ANC"]["vs_ref"] == "below_local_lower"
    assert facts["PLT"]["vs_ref"] == "below_local_lower"

    assert any(
        trend["analyte"] == "PLT"
        and trend["direction"] == "down"
        and trend["verdict"] == "substantial"
        for trend in result["supporting_trends"]
    )
    assert any(atom["type"] == "intervention_target" for atom in result["reasoning_atoms"])


def test_reconstruct_dataset_keeps_review_only_cases():
    repo = DataRepository(FIXTURE_DIR)
    result = reconstruct_dataset(repo)

    assert result["summary"]["num_cases"] == 2
    assert result["summary"]["uses_doctor_gold"] is True
    assert len(result["reconstructions"]) == 2


@pytest.mark.skipif(not PRIVATE_REVIEWED_DIR.exists(), reason="private reviewed dataset is not present")
def test_private_reviewed_dataset_reconstructs_all_current_doctor_comments():
    repo = DataRepository(PRIVATE_REVIEWED_DIR)
    result = reconstruct_dataset(repo)

    assert result["summary"]["num_cases"] == len(repo.case_records)
    assert result["summary"]["num_cases"] == 15
    assert result["summary"]["num_out_of_phase1"] == 2
    assert any(
        note["status"] == "preserved_out_of_phase1"
        for reconstruction in result["reconstructions"]
        for note in reconstruction["scope_notes"]
    )
