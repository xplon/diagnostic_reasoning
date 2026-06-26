from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from diagnostic_reasoning.io import load_json, write_json


def _domain(report_type: str | None) -> str:
    if not report_type:
        return "unknown"
    value = report_type.lower()
    if value in {"cbc", "blood_routine", "blood_count"}:
        return "cbc"
    if value in {"biochemistry", "liver_kidney", "chemistry"}:
        return "biochemistry"
    return value


def _map_ids(items: list[str], prefix: str) -> dict[str, str]:
    return {old: f"{prefix}_{idx:04d}" for idx, old in enumerate(items, start=1)}


def promote_staging(
    staging_dir: str | Path,
    output_dir: str | Path,
    mark_verified: bool = True,
    strip_private_image_paths: bool = True,
) -> dict[str, Any]:
    staging_dir = Path(staging_dir)
    output_dir = Path(output_dir)

    labs_doc = load_json(staging_dir / "verified_lab_drafts.json")
    timelines_doc = load_json(staging_dir / "patient_timelines_draft.json")
    cases_doc = load_json(staging_dir / "case_records_draft.json")
    summary_doc = load_json(staging_dir / "ingest_summary.json")

    labs = labs_doc["verified_labs"]
    timelines = timelines_doc["patient_timelines"]
    cases = cases_doc["case_records"]

    timeline_id_map = _map_ids([t["patient_timeline_id"] for t in timelines], "ptl_v0")
    patient_id_map = {old: f"pt_v0_{idx:04d}" for idx, old in enumerate(timeline_id_map.keys(), start=1)}
    report_id_map = _map_ids([lab["verified_lab_id"] for lab in labs], "report_v0")
    case_id_map = _map_ids([case["case_id"] for case in cases], "case_v0")

    reports_out = []
    for lab in labs:
        source = deepcopy(lab.get("source", {}))
        raw_case_id = lab.get("raw_case_id")
        if strip_private_image_paths:
            source.pop("image_path", None)
            source["private_image_ref"] = raw_case_id
        if mark_verified:
            source["human_verified"] = True
            source["extraction_status"] = "owner_verified_from_staging"
        fields = deepcopy(lab.get("fields", {}))
        for field in fields.values():
            if field.get("ref_source") == "local_report":
                field["ref_source"] = "report"
            if mark_verified and field.get("value") is not None:
                field["needs_review"] = False
                field["confidence"] = max(float(field.get("confidence", 0.0)), 0.99)
                if field.get("source_text", "").startswith("AI visual transcription"):
                    field["source_text"] = "owner verified from private staging dataset"
        timeline_old = lab["patient_timeline_id"]
        report = {
            "report_id": report_id_map[lab["verified_lab_id"]],
            "patient_id": patient_id_map[timeline_old],
            "patient_timeline_id": timeline_id_map[timeline_old],
            "report_domain": _domain(source.get("report_type")),
            "report_type": source.get("report_type", "unknown"),
            "collected_at": lab.get("report_time"),
            "sample_time": lab.get("sample_time"),
            "source": {
                "report_type": source.get("report_type", "unknown"),
                "ocr_method": source.get("ocr_method", "manual"),
                "human_verified": bool(source.get("human_verified")),
                "private_image_ref": source.get("private_image_ref"),
                "source_markdown": source.get("source_markdown"),
                "extraction_status": source.get("extraction_status"),
            },
            "fields": fields,
            "doctor_comment_verbatim": lab.get("doctor_comment_verbatim"),
            "report_notes": lab.get("report_notes", []),
            "provenance": {
                "staging_verified_lab_id": lab["verified_lab_id"],
                "raw_case_id": raw_case_id,
                "out_of_scope_for_phase1_cbc": lab.get("out_of_scope_for_phase1_cbc", False),
            },
        }
        reports_out.append(report)

    timelines_out = []
    for timeline in timelines:
        old_timeline_id = timeline["patient_timeline_id"]
        events = []
        for idx, event in enumerate(timeline.get("events", []), start=1):
            payload = deepcopy(event)
            old_report_id = payload.pop("verified_lab_id", None)
            raw_case_id = payload.get("raw_case_id")
            payload.pop("source_image_path", None)
            if old_report_id:
                payload["report_id"] = report_id_map[old_report_id]
            events.append(
                {
                    "event_id": f"{timeline_id_map[old_timeline_id]}_event_{idx:04d}",
                    "event_type": "lab" if event.get("event_type") == "lab_report" else event.get("event_type"),
                    "t": event.get("report_time"),
                    "payload": payload,
                    "provenance": {"raw_case_id": raw_case_id},
                }
            )
        timelines_out.append(
            {
                "patient_timeline_id": timeline_id_map[old_timeline_id],
                "patient_id": patient_id_map[old_timeline_id],
                "baseline": timeline.get("patient_state", {}),
                "events": events,
                "grouping": timeline.get("grouping", {}),
                "provenance": {
                    "staging_patient_timeline_id": old_timeline_id,
                    "raw_case_ids": timeline.get("raw_case_ids", []),
                    "verified_lab_ids": [report_id_map[v] for v in timeline.get("verified_lab_ids", [])],
                },
            }
        )

    cases_out = []
    for case in cases:
        old_timeline_id = case["patient_timeline_id"]
        comments = case.get("doctor_gold", {}).get("comments", [])
        recommendation = "\n".join(c.get("doctor_comment_verbatim", "") for c in comments).strip()
        cases_out.append(
            {
                "case_id": case_id_map[case["case_id"]],
                "patient_id": patient_id_map[old_timeline_id],
                "patient_timeline_id": timeline_id_map[old_timeline_id],
                "target_report_id": report_id_map[case["target_lab_id"]],
                "related_report_ids": [report_id_map[rid] for rid in case.get("related_lab_ids", [])],
                "evaluation_eligible": case.get("evaluation_eligible", True),
                "report_scope": case.get("report_scope", "unknown"),
                "split": case.get("split_suggestion", "development"),
                "doctor_gold_recommendation": recommendation,
                "gold_actions": case.get("doctor_gold", {}).get("gold_actions", []),
                "gold_reasoning_atoms": case.get("gold_reasoning_atoms", []),
                "ai_output": {"candidate_actions": [], "reasoning_atoms": [], "safety_violations": []},
                "metadata": {
                    "source_case_id": case["case_id"],
                    "source_raw_case_ids": case.get("source_raw_case_ids", []),
                    "learning_layer": case.get("learning_layer", {}),
                    "mapping_notes": case.get("mapping_notes"),
                    "expected_output_constraints": case.get("expected_output_constraints", []),
                },
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    dataset_summary = {
        "generated_at": generated_at,
        "source_staging_dir": str(staging_dir),
        "mark_verified": mark_verified,
        "strip_private_image_paths": strip_private_image_paths,
        "counts": {
            "reports": len(reports_out),
            "patient_timelines": len(timelines_out),
            "case_records": len(cases_out),
            "evaluation_eligible_case_records": sum(1 for c in cases_out if c["evaluation_eligible"]),
        },
        "source_counts": summary_doc.get("counts", {}),
        "notes": [
            "CBC remains the first implemented report_domain; non-CBC reports are preserved for broader diagnostic-sheet reasoning.",
            "Private image paths are replaced by private_image_ref when strip_private_image_paths=true.",
            "Doctor medication/dose text remains case-specific gold evidence, not a reusable prescription rule.",
        ],
    }

    write_json(output_dir / "reports.json", {"generated_at": generated_at, "reports": reports_out})
    write_json(output_dir / "patient_timelines.json", {"generated_at": generated_at, "patient_timelines": timelines_out})
    write_json(output_dir / "case_records.json", {"generated_at": generated_at, "case_records": cases_out})
    write_json(output_dir / "dataset_summary.json", dataset_summary)
    return dataset_summary
