from __future__ import annotations

from diagnostic_reasoning.evaluation import score_actions, score_reasoning_atoms


def test_action_exact_and_partial():
    exact = score_actions(["monitoring_review"], ["monitoring_review"])
    assert exact["label"] == "exact"
    context_status = score_actions(["monitoring_review", "insufficient_context"], ["monitoring_review"])
    assert context_status["label"] == "exact"
    partial = score_actions(["monitoring_review", "anemia_review"], ["monitoring_review"])
    assert partial["label"] == "partial"


def test_atom_match_fact_and_trend_f1():
    pred = [
        {"type": "fact", "analyte": "ANC", "vs_ref": "below_local_lower"},
        {"type": "trend", "analyte": "PLT", "direction": "down", "verdict": "substantial"},
    ]
    gold = [
        {"type": "fact", "analyte": "ANC", "vs_ref": "below_local_lower"},
        {"type": "trend", "analyte": "PLT", "direction": "down", "verdict": "substantial"},
    ]
    score = score_reasoning_atoms(pred, gold)
    assert score["f1"] == 1.0
