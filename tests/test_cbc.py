from __future__ import annotations

import json
from pathlib import Path

from diagnostic_reasoning.domains.cbc import grade_field, normalize_field


def test_ctcae_golden_cases():
    data = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "ctcae_golden_cases.json").read_text(encoding="utf-8"))
    for case in data["cases"]:
        field = normalize_field(case["analyte"], {"value": case["value"], "unit": case["unit"], "ref": case["ref"]})
        if "expected_value" in case:
            assert field["value"] == case["expected_value"]
        grade = grade_field(case["analyte"], field)
        assert grade.grade == case["expected_grade"], case
        assert grade.grading_source == "CTCAE v5.0"


def test_hb_gdl_to_gl_conversion():
    field = normalize_field("Hb", {"value": 12.7, "unit": "g/dL", "ref": [11.5, 15.0]})
    assert field["value"] == 127.0
    assert field["unit"] == "g/L"
    assert field["ref"] == [115.0, 150.0]
