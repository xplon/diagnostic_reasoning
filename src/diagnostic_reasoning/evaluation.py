from __future__ import annotations

from typing import Any


def _action_name(action: Any) -> str:
    if isinstance(action, str):
        return action
    if isinstance(action, dict):
        return action.get("action") or action.get("action_type") or ""
    return str(action)


def score_actions(pred_actions: list[Any], gold_actions: list[str], boundary_issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    gold = set(gold_actions)
    pred = {_action_name(a) for a in pred_actions if _action_name(a)}
    if "insufficient_context" not in gold:
        pred.discard("insufficient_context")
    gold = set(gold_actions)
    blocks = [i for i in boundary_issues or [] if i.get("severity") == "block"]
    if blocks:
        label = "unsafe"
    elif pred == gold:
        label = "exact"
    elif pred & gold:
        label = "partial"
    else:
        label = "mismatch"
    return {
        "label": label,
        "exact": label == "exact",
        "partial": label in {"exact", "partial"},
        "pred_actions": sorted(pred),
        "gold_actions": sorted(gold),
    }


def _atom_type(atom: dict[str, Any]) -> str:
    return atom.get("type") or atom.get("atom_type") or ""


def atom_matches(pred: dict[str, Any], gold: dict[str, Any]) -> bool:
    if _atom_type(pred) != _atom_type(gold):
        return False
    analyte_pred = pred.get("analyte") or pred.get("field")
    analyte_gold = gold.get("analyte") or gold.get("field")
    if analyte_pred and analyte_gold and analyte_pred != analyte_gold:
        return False
    atom_type = _atom_type(gold)
    if atom_type == "fact":
        def fact_ref(atom: dict[str, Any]) -> str | None:
            value = atom.get("vs_ref") or atom.get("flag")
            return {
                "normal": "within_local",
                "low": "below_local_lower",
                "high": "above_local_upper",
            }.get(value, value)

        return fact_ref(pred) == fact_ref(gold)
    if atom_type == "trend":
        return pred.get("direction") == gold.get("direction") and pred.get("verdict") == gold.get("verdict")
    if atom_type == "intervention_target":
        return (pred.get("action") or pred.get("candidate_action")) == (gold.get("action") or gold.get("candidate_action"))
    if atom_type == "safety_gap":
        return pred.get("missing") == gold.get("missing")
    return True


def score_reasoning_atoms(pred_atoms: list[dict[str, Any]], gold_atoms: list[dict[str, Any]]) -> dict[str, Any]:
    matched_gold: set[int] = set()
    matches = 0
    for pred in pred_atoms:
        for idx, gold in enumerate(gold_atoms):
            if idx in matched_gold:
                continue
            if atom_matches(pred, gold):
                matched_gold.add(idx)
                matches += 1
                break
    precision = matches / len(pred_atoms) if pred_atoms else 0.0
    recall = matches / len(gold_atoms) if gold_atoms else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "matches": matches,
        "pred_count": len(pred_atoms),
        "gold_count": len(gold_atoms),
    }


def evaluate_case(case_record: dict[str, Any], ai_output: dict[str, Any] | None = None) -> dict[str, Any]:
    ai = ai_output or case_record.get("ai_output") or {}
    action_score = score_actions(ai.get("candidate_actions", []), case_record.get("gold_actions", []), ai.get("safety_violations", []))
    atom_score = score_reasoning_atoms(ai.get("reasoning_atoms", []), case_record.get("gold_reasoning_atoms", []))
    return {
        "case_id": case_record["case_id"],
        "action_score": action_score,
        "atom_score": atom_score,
    }


def evaluate_dataset(case_records: list[dict[str, Any]], outputs_by_case: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    outputs_by_case = outputs_by_case or {}
    results = [evaluate_case(case, outputs_by_case.get(case["case_id"])) for case in case_records if case.get("evaluation_eligible", True)]
    total = len(results) or 1
    exact = sum(1 for r in results if r["action_score"]["label"] == "exact")
    partial = sum(1 for r in results if r["action_score"]["partial"])
    avg_f1 = sum(r["atom_score"]["f1"] for r in results) / total
    unsafe = sum(1 for r in results if r["action_score"]["label"] == "unsafe")
    return {
        "summary": {
            "num_cases": len(results),
            "action_exact_match_rate": round(exact / total, 4),
            "action_partial_match_rate": round(partial / total, 4),
            "reasoning_atom_f1": round(avg_f1, 4),
            "unsafe_recommendation_rate": round(unsafe / total, 4),
        },
        "cases": results,
    }
