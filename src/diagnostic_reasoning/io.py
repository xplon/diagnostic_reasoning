from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_dataset(data_dir: str | Path) -> dict[str, Any]:
    data_dir = Path(data_dir)
    return {
        "reports": load_json(data_dir / "reports.json").get("reports", []),
        "patient_timelines": load_json(data_dir / "patient_timelines.json").get("patient_timelines", []),
        "case_records": load_json(data_dir / "case_records.json").get("case_records", []),
    }


class DataRepository:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        dataset = load_dataset(self.data_dir)
        self.reports = dataset["reports"]
        self.timelines = dataset["patient_timelines"]
        self.case_records = dataset["case_records"]
        self.reports_by_id = {r["report_id"]: r for r in self.reports}
        self.timelines_by_id = {t["patient_timeline_id"]: t for t in self.timelines}
        self.cases_by_id = {c["case_id"]: c for c in self.case_records}

    def get_case(self, case_id: str) -> dict[str, Any]:
        try:
            return self.cases_by_id[case_id]
        except KeyError as exc:
            raise KeyError(f"Unknown case_id: {case_id}") from exc

    def get_report(self, report_id: str) -> dict[str, Any]:
        try:
            return self.reports_by_id[report_id]
        except KeyError as exc:
            raise KeyError(f"Unknown report_id: {report_id}") from exc

    def get_timeline(self, timeline_id: str) -> dict[str, Any]:
        try:
            return self.timelines_by_id[timeline_id]
        except KeyError as exc:
            raise KeyError(f"Unknown patient_timeline_id: {timeline_id}") from exc
