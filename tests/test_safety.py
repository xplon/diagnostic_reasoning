from __future__ import annotations

import json
from pathlib import Path

from diagnostic_reasoning.safety import recommendation_boundary_check


def test_all_redteam_cases_detected():
    data = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "safety_redteam_cases.json").read_text(encoding="utf-8"))
    for case in data["cases"]:
        state = case.get("state", {})
        if case.get("missing_context"):
            state["missing_context"] = case["missing_context"]
        issues = recommendation_boundary_check(case["text"], state)
        kinds = {issue.kind for issue in issues}
        assert case["expected_kind"] in kinds, case


def test_safe_physician_review_language_not_blocked():
    text = "以下为医生审核用候选建议：结合ANC低和治疗时间，考虑中性粒支持评估，需医生确认。"
    issues = recommendation_boundary_check(text, {"missing_context": []})
    assert not [issue for issue in issues if issue.severity == "block"]
