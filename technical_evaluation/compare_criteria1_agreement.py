from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


DEFAULT_GPT_DIR = Path("technical_evaluation/results/GPT")
DEFAULT_DEEPSEEK_DIR = Path("technical_evaluation/results/Deepseek")
DEFAULT_BASELINE_GPT_DIR = Path("technical_evaluation/results/baseline/GPT")
DEFAULT_BASELINE_DEEPSEEK_DIR = Path("technical_evaluation/results/baseline/Deepseek")
DEFAULT_HUMAN_FILE = Path("technical_evaluation/results/Yukun_criteria1_annotations.json")
DEFAULT_FIXED_GROUND_TRUTH_FILE = Path("technical_evaluation/results/criteria1_persona_redesign_preview.json")
DEFAULT_OUTPUT_FILE = Path("technical_evaluation/results/criteria1_gpt5_deepseek_human_metrics.json")

SUPPORTED_LABELS = ("pass", "partial", "fail")

FIXED_GROUND_TRUTH_BUCKET_TO_LABEL: Dict[str, str] = {
    "satisfy": "pass",
    "not_satisfy": "fail",
}

SOURCE_FIELD_TO_STEP_KEYS: Dict[str, Sequence[str]] = {
    "evaluation": ("EVALUATION",),
    "memory": ("MEMORY",),
    "thinking process": ("AI REASONING",),
    "next goal": ("TARGET OBJECTIVE",),
    "action": ("ACTION",),
}

SOURCE_FIELD_ALIASES: Dict[str, str] = {
    "evaluation": "evaluation",
    "memory": "memory",
    "thinking": "thinking process",
    "thinking process": "thinking process",
    "thinking_process": "thinking process",
    "next goal": "next goal",
    "next_goal": "next goal",
    "action": "action",
}


def _drop_none_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _normalize_label(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text in {"pass", "partial", "fail"}:
        return text
    return None


def _extract_criteria1_label(record: Dict[str, Any]) -> Optional[str]:
    # Prefer the direct summary field if present.
    criteria1 = record.get("criteria1_evaluation")
    if isinstance(criteria1, dict):
        label = _normalize_label(criteria1.get("overall_assessment"))
        if label is not None:
            return label

    # Fallback to nested criteria list.
    judge_eval = record.get("judge_evaluation")
    if isinstance(judge_eval, dict):
        criteria_results = judge_eval.get("criteria_results")
        if isinstance(criteria_results, list):
            for item in criteria_results:
                if not isinstance(item, dict):
                    continue
                source_key = str(item.get("source_key") or "").strip().lower()
                title = str(item.get("title") or "").strip().lower()
                if source_key == "criteria1" or title == "criteria1":
                    label = _normalize_label(item.get("overall_assessment"))
                    if label is not None:
                        return label

    return None


def _extract_criteria1_result(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    criteria1 = record.get("criteria1_evaluation")
    if isinstance(criteria1, dict):
        return criteria1

    judge_eval = record.get("judge_evaluation")
    if isinstance(judge_eval, dict):
        criteria_results = judge_eval.get("criteria_results")
        if isinstance(criteria_results, list):
            for item in criteria_results:
                if not isinstance(item, dict):
                    continue
                source_key = str(item.get("source_key") or "").strip().lower()
                title = str(item.get("title") or "").strip().lower()
                if source_key == "criteria1" or title == "criteria1":
                    return item

    return None


def _extract_model_evidence(criteria1_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence_rows: List[Dict[str, Any]] = []
    involved_steps = criteria1_result.get("involved_steps")
    if not isinstance(involved_steps, list):
        return evidence_rows

    for phase in involved_steps:
        if not isinstance(phase, dict):
            continue

        phase_status = _normalize_label(phase.get("evaluateStatus"))
        phase_steps = phase.get("steps") if isinstance(phase.get("steps"), list) else None
        highlighted = phase.get("highlighted_evidence")
        if not isinstance(highlighted, list):
            continue

        for item in highlighted:
            if not isinstance(item, dict):
                continue

            row = _drop_none_fields(
                {
                    "phase_status": phase_status,
                    "phase_steps": phase_steps,
                    "step_index": item.get("step_index"),
                    "source_field": item.get("source_field"),
                    "verdict": _normalize_label(item.get("verdict")),
                    "text": item.get("highlighted_text"),
                    "reasoning": item.get("reasoning"),
                }
            )
            evidence_rows.append(row)

    return evidence_rows


def _extract_model_case(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    criteria1_result = _extract_criteria1_result(record)
    if not isinstance(criteria1_result, dict):
        return None

    label = _normalize_label(criteria1_result.get("overall_assessment"))
    if label is None:
        return None

    raw_reasoning = criteria1_result.get("overall_reasoning")
    reasoning = str(raw_reasoning).strip() if raw_reasoning is not None else None
    if reasoning == "":
        reasoning = None

    source_file = record.get("source_file")
    source_file_text = str(source_file).strip() if source_file is not None else None
    if source_file_text == "":
        source_file_text = None

    return {
        "overall_assessment": label,
        "overall_reasoning": reasoning,
        "evidence": _extract_model_evidence(criteria1_result),
        "source_file": source_file_text,
    }


def _extract_human_evidence(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence_rows: List[Dict[str, Any]] = []
    evidences = item.get("evidences")
    if not isinstance(evidences, list):
        return evidence_rows

    for evidence in evidences:
        if not isinstance(evidence, dict):
            continue
        row = _drop_none_fields(
            {
                "step_id": evidence.get("step_id"),
                "field": evidence.get("field"),
                "verdict": _normalize_label(evidence.get("verdict")),
                "text": evidence.get("text"),
            }
        )
        evidence_rows.append(row)

    return evidence_rows


def _extract_human_step_labels(item: Dict[str, Any]) -> Dict[int, str]:
    labels: Dict[int, str] = {}
    raw_step_labels = item.get("step_labels")
    if not isinstance(raw_step_labels, dict):
        return labels

    for raw_step_id, raw_label in raw_step_labels.items():
        label = _normalize_label(raw_label)
        if label is None:
            continue

        step_id: Optional[int] = None
        if isinstance(raw_step_id, int):
            step_id = raw_step_id
        elif isinstance(raw_step_id, str) and raw_step_id.strip().isdigit():
            step_id = int(raw_step_id.strip())

        if step_id is None:
            continue
        labels[step_id] = label

    return labels


def _load_model_cases(results_dir: Path) -> Dict[str, Dict[str, Any]]:
    cases_by_data_id: Dict[str, Dict[str, Any]] = {}
    for json_file in sorted(results_dir.rglob("*__evaluated.json")):
        if not json_file.is_file():
            continue
        try:
            record = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(record, dict):
            continue

        data_id = str(record.get("data_id") or "").strip()
        if not data_id:
            continue

        case = _extract_model_case(record)
        if case is None:
            continue

        cases_by_data_id[data_id] = case
    return cases_by_data_id


def _load_model_labels(results_dir: Path) -> Dict[str, str]:
    return {
        data_id: str(case["overall_assessment"])
        for data_id, case in _load_model_cases(results_dir).items()
        if "overall_assessment" in case
    }


def _load_human_cases(human_file: Path) -> Dict[str, Dict[str, Any]]:
    source = json.loads(human_file.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise ValueError("Human annotation file must be a JSON object")

    annotations = source.get("annotations")
    if not isinstance(annotations, dict):
        raise ValueError("Human annotation file missing object field: annotations")

    cases_by_data_id: Dict[str, Dict[str, Any]] = {}
    for data_id, item in annotations.items():
        if not isinstance(item, dict):
            continue

        label = _normalize_label(item.get("overall_assessment"))
        if label is None:
            continue

        raw_reasoning = item.get("overall_reasoning")
        reasoning = str(raw_reasoning).strip() if raw_reasoning is not None else None
        if reasoning == "":
            reasoning = None

        cases_by_data_id[str(data_id)] = {
            "overall_assessment": label,
            "overall_reasoning": reasoning,
            "evidence": _extract_human_evidence(item),
            "step_labels": _extract_human_step_labels(item),
        }

    return cases_by_data_id


def _load_human_labels(human_file: Path) -> Dict[str, str]:
    return {
        data_id: str(case["overall_assessment"])
        for data_id, case in _load_human_cases(human_file).items()
        if "overall_assessment" in case
    }


def _normalize_fixed_ground_truth_bucket(raw: Any) -> Optional[str]:
    text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    return FIXED_GROUND_TRUTH_BUCKET_TO_LABEL.get(text)


def _extract_source_stem(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None
    stem = Path(text).stem.strip()
    if not stem:
        return None
    return stem


def _load_fixed_ground_truth_cases(fixed_ground_truth_file: Path) -> Dict[str, Dict[str, Any]]:
    source = json.loads(fixed_ground_truth_file.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise ValueError("Fixed ground truth file must be a JSON object")

    items = source.get("items")
    if not isinstance(items, list):
        raise ValueError("Fixed ground truth file missing list field: items")

    cases_by_source_stem: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue

        label = _normalize_fixed_ground_truth_bucket(item.get("bucket"))
        if label is None:
            continue

        source_stem = _extract_source_stem(item.get("file"))
        if source_stem is None:
            continue

        raw_file = item.get("file")
        file_name = Path(str(raw_file)).name if raw_file is not None else None

        cases_by_source_stem[source_stem] = _drop_none_fields(
            {
                "source_stem": source_stem,
                "dataset_file": file_name,
                "persona": item.get("persona"),
                "bucket": str(item.get("bucket") or "").strip(),
                "overall_assessment": label,
                "criteria1": item.get("criteria1"),
            }
        )

    return cases_by_source_stem


def _index_model_cases_by_source_stem(model_cases: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    indexed_cases: Dict[str, Dict[str, Any]] = {}
    for case in model_cases.values():
        if not isinstance(case, dict):
            continue

        source_stem = _extract_source_stem(case.get("source_file"))
        if source_stem is None:
            continue

        indexed_cases[source_stem] = case

    return indexed_cases


def _empty_fixed_ground_truth_metrics(
    label_space: Sequence[str],
    model_distribution_key: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "fixed_ground_truth_total": 0,
        "covered_cases": 0,
        "missing_cases": 0,
        "coverage_rate": None,
        "accuracy": None,
        "macro_f1": None,
        "cohens_kappa": None,
        "ground_truth_distribution": _label_distribution([], label_space),
        model_distribution_key: _label_distribution([], label_space),
        "confusion_matrix": _confusion_matrix([], [], label_space),
        "disagreement_count": 0,
        "disagreement_cases": [],
        "missing_case_details": [],
    }


def _build_fixed_ground_truth_metrics(
    model_cases: Dict[str, Dict[str, Any]],
    fixed_ground_truth_cases: Dict[str, Dict[str, Any]],
    label_space: Sequence[str],
    model_name: str,
    model_distribution_key: str,
) -> Dict[str, Any]:
    if not fixed_ground_truth_cases:
        return _empty_fixed_ground_truth_metrics(
            label_space=label_space,
            model_distribution_key=model_distribution_key,
            reason="fixed_ground_truth_not_loaded",
        )

    model_cases_by_source_stem = _index_model_cases_by_source_stem(model_cases)

    compared_source_stems: List[str] = []
    fixed_eval: List[str] = []
    model_eval: List[str] = []
    disagreement_cases: List[Dict[str, Any]] = []

    for source_stem in sorted(set(fixed_ground_truth_cases.keys()) & set(model_cases_by_source_stem.keys())):
        fixed_case = fixed_ground_truth_cases[source_stem]
        model_case = model_cases_by_source_stem[source_stem]

        fixed_label = _normalize_label(fixed_case.get("overall_assessment"))
        predicted_label = _normalize_label(model_case.get("overall_assessment"))
        if fixed_label is None or predicted_label is None:
            continue

        compared_source_stems.append(source_stem)
        fixed_eval.append(fixed_label)
        model_eval.append(predicted_label)

        if fixed_label != predicted_label:
            disagreement_cases.append(
                _drop_none_fields(
                    {
                        "source_stem": source_stem,
                        "dataset_file": fixed_case.get("dataset_file"),
                        "persona": fixed_case.get("persona"),
                        "ground_truth_bucket": fixed_case.get("bucket"),
                        "ground_truth_overall_assessment": fixed_label,
                        "ground_truth_criteria1": fixed_case.get("criteria1"),
                        f"{model_name}_overall_assessment": predicted_label,
                        f"{model_name}_overall_reasoning": model_case.get("overall_reasoning"),
                        f"{model_name}_source_file": model_case.get("source_file"),
                    }
                )
            )

    missing_source_stems = sorted(set(fixed_ground_truth_cases.keys()) - set(model_cases_by_source_stem.keys()))
    missing_case_details = [fixed_ground_truth_cases[source_stem] for source_stem in missing_source_stems]

    return {
        "available": True,
        "fixed_ground_truth_total": len(fixed_ground_truth_cases),
        "covered_cases": len(compared_source_stems),
        "missing_cases": len(missing_case_details),
        "coverage_rate": (
            len(compared_source_stems) / len(fixed_ground_truth_cases)
            if fixed_ground_truth_cases
            else None
        ),
        "accuracy": _accuracy(fixed_eval, model_eval),
        "macro_f1": _macro_f1(fixed_eval, model_eval, label_space),
        "cohens_kappa": _cohens_kappa(fixed_eval, model_eval, label_space),
        "ground_truth_distribution": _label_distribution(fixed_eval, label_space),
        model_distribution_key: _label_distribution(model_eval, label_space),
        "confusion_matrix": _confusion_matrix(fixed_eval, model_eval, label_space),
        "disagreement_count": len(disagreement_cases),
        "disagreement_cases": disagreement_cases,
        "missing_case_details": missing_case_details,
    }


def _accuracy(y_true: Sequence[str], y_pred: Sequence[str]) -> Optional[float]:
    n = len(y_true)
    if n == 0:
        return None
    correct = sum(1 for a, b in zip(y_true, y_pred) if a == b)
    return correct / n


def _cohens_kappa(y_a: Sequence[str], y_b: Sequence[str], labels: Iterable[str]) -> Optional[float]:
    n = len(y_a)
    if n == 0:
        return None

    labels_list = list(labels)
    if not labels_list:
        return None

    agree = sum(1 for a, b in zip(y_a, y_b) if a == b)
    p0 = agree / n

    counts_a = {label: 0 for label in labels_list}
    counts_b = {label: 0 for label in labels_list}
    for a, b in zip(y_a, y_b):
        if a in counts_a:
            counts_a[a] += 1
        if b in counts_b:
            counts_b[b] += 1

    pe = 0.0
    for label in labels_list:
        pe += (counts_a[label] / n) * (counts_b[label] / n)

    if pe >= 1.0:
        return None
    return (p0 - pe) / (1.0 - pe)


def _confusion_matrix(y_true: Sequence[str], y_pred: Sequence[str], labels: Iterable[str]) -> Dict[str, Dict[str, int]]:
    labels_list = list(labels)
    matrix: Dict[str, Dict[str, int]] = {
        true_label: {pred_label: 0 for pred_label in labels_list} for true_label in labels_list
    }

    for true_label, pred_label in zip(y_true, y_pred):
        if true_label not in matrix:
            continue
        if pred_label not in matrix[true_label]:
            continue
        matrix[true_label][pred_label] += 1

    return matrix


def _macro_f1(y_true: Sequence[str], y_pred: Sequence[str], labels: Iterable[str]) -> Optional[float]:
    labels_list = list(labels)
    if len(y_true) == 0 or not labels_list:
        return None

    f1_values: List[float] = []
    for label in labels_list:
        tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == label and yp == label)
        fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt != label and yp == label)
        fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == label and yp != label)

        if tp == 0 and fp == 0 and fn == 0:
            # Label absent in both true and pred for this comparison; ignore.
            continue

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = (2 * precision * recall) / (precision + recall)
        f1_values.append(f1)

    if not f1_values:
        return None
    return sum(f1_values) / len(f1_values)


def _label_distribution(labels: Sequence[str], known_labels: Iterable[str]) -> Dict[str, int]:
    distribution = {label: 0 for label in known_labels}
    for label in labels:
        if label in distribution:
            distribution[label] += 1
    return distribution


def _normalize_source_field_for_matching(raw: Any) -> Optional[str]:
    text = str(raw or "").strip().lower().replace("-", " ")
    text = " ".join(text.split())
    if not text:
        return None
    return SOURCE_FIELD_ALIASES.get(text)


def _step_text_candidates(step: Dict[str, Any], normalized_source_field: Optional[str]) -> List[str]:
    keys: List[str] = []
    if normalized_source_field and normalized_source_field in SOURCE_FIELD_TO_STEP_KEYS:
        keys.extend(SOURCE_FIELD_TO_STEP_KEYS[normalized_source_field])
    else:
        for source_keys in SOURCE_FIELD_TO_STEP_KEYS.values():
            keys.extend(source_keys)

    candidates: List[str] = []
    for key in keys:
        value = step.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    return candidates


def _collect_candidate_step_indices(steps: Sequence[Any], raw_step_index: Any) -> List[int]:
    indices: List[int] = []

    step_index: Optional[int] = None
    if isinstance(raw_step_index, int):
        step_index = raw_step_index
    elif isinstance(raw_step_index, str) and raw_step_index.strip().isdigit():
        step_index = int(raw_step_index.strip())

    if step_index is not None:
        if 0 <= step_index < len(steps):
            indices.append(step_index)
        if step_index >= 1 and (step_index - 1) < len(steps):
            indices.append(step_index - 1)

        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            raw_step_id = step.get("step_id")
            if isinstance(raw_step_id, int) and raw_step_id == step_index:
                indices.append(idx)
            elif isinstance(raw_step_id, str) and raw_step_id.strip().isdigit() and int(raw_step_id.strip()) == step_index:
                indices.append(idx)

    unique_indices: List[int] = []
    seen = set()
    for idx in indices:
        if idx in seen:
            continue
        seen.add(idx)
        unique_indices.append(idx)

    if unique_indices:
        return unique_indices
    return [idx for idx in range(len(steps))]


def _evidence_text_is_grounded_in_record(
    record: Dict[str, Any],
    evidence_text: str,
    raw_step_index: Any,
    raw_source_field: Any,
) -> bool:
    steps = record.get("steps")
    if not isinstance(steps, list) or not steps:
        return False

    normalized_source_field = _normalize_source_field_for_matching(raw_source_field)
    for step_idx in _collect_candidate_step_indices(steps, raw_step_index):
        step = steps[step_idx]
        if not isinstance(step, dict):
            continue
        source_texts = _step_text_candidates(step, normalized_source_field)
        for source_text in source_texts:
            if evidence_text in source_text:
                return True
    return False


def _compute_evidence_substring_accuracy(results_dir: Path, model_name: str) -> Dict[str, Any]:
    if not results_dir.exists():
        return {
            "model": model_name,
            "results_dir": str(results_dir),
            "available": False,
            "reason": "results_dir_not_found",
            "evidence_items_total": 0,
            "substring_grounded_items": 0,
            "substring_grounding_accuracy": None,
            "cases_with_evidence": 0,
            "cases_all_evidence_grounded": 0,
            "case_all_grounded_rate": None,
            "ungrounded_examples": [],
        }

    total_items = 0
    grounded_items = 0
    cases_with_evidence = 0
    cases_all_grounded = 0
    ungrounded_examples: List[Dict[str, Any]] = []

    for json_file in sorted(results_dir.rglob("*__evaluated.json")):
        if not json_file.is_file():
            continue
        try:
            record = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(record, dict):
            continue

        criteria1_result = _extract_criteria1_result(record)
        if not isinstance(criteria1_result, dict):
            continue

        involved_steps = criteria1_result.get("involved_steps")
        if not isinstance(involved_steps, list):
            continue

        case_total = 0
        case_grounded = 0

        for phase in involved_steps:
            if not isinstance(phase, dict):
                continue
            highlighted = phase.get("highlighted_evidence")
            if not isinstance(highlighted, list):
                continue

            for item in highlighted:
                if not isinstance(item, dict):
                    continue

                highlighted_text = str(item.get("highlighted_text") or "").strip()
                if not highlighted_text:
                    continue

                case_total += 1
                total_items += 1

                is_grounded = _evidence_text_is_grounded_in_record(
                    record=record,
                    evidence_text=highlighted_text,
                    raw_step_index=item.get("step_index"),
                    raw_source_field=item.get("source_field"),
                )
                if is_grounded:
                    case_grounded += 1
                    grounded_items += 1
                elif len(ungrounded_examples) < 20:
                    ungrounded_examples.append(
                        {
                            "data_id": str(record.get("data_id") or ""),
                            "source_file": record.get("source_file"),
                            "step_index": item.get("step_index"),
                            "source_field": item.get("source_field"),
                            "text": highlighted_text,
                        }
                    )

        if case_total > 0:
            cases_with_evidence += 1
            if case_total == case_grounded:
                cases_all_grounded += 1

    return {
        "model": model_name,
        "results_dir": str(results_dir),
        "available": True,
        "method": "substring_match_against_original_step_field_text",
        "evidence_items_total": total_items,
        "substring_grounded_items": grounded_items,
        "substring_grounding_accuracy": (grounded_items / total_items) if total_items > 0 else None,
        "cases_with_evidence": cases_with_evidence,
        "cases_all_evidence_grounded": cases_all_grounded,
        "case_all_grounded_rate": (cases_all_grounded / cases_with_evidence) if cases_with_evidence > 0 else None,
        "ungrounded_examples": ungrounded_examples,
    }


def _parse_int(raw: Any) -> Optional[int]:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.isdigit():
            return int(text)
    return None


def _resolve_step_id_candidates_from_record(record: Dict[str, Any], raw_step_index: Any) -> List[int]:
    steps = record.get("steps")
    if not isinstance(steps, list) or not steps:
        return []

    step_ids: List[int] = []
    for idx in _collect_candidate_step_indices(steps, raw_step_index):
        step = steps[idx]
        if not isinstance(step, dict):
            continue

        raw_step_id = step.get("step_id")
        step_id = _parse_int(raw_step_id)
        if step_id is None:
            # Fallback to a 1-based index if step_id is missing.
            step_id = idx + 1
        step_ids.append(step_id)

    # Additional fallback: model might directly output 1-based step ids.
    direct_step = _parse_int(raw_step_index)
    if direct_step is not None and direct_step > 0:
        step_ids.append(direct_step)

    unique_step_ids: List[int] = []
    seen = set()
    for step_id in step_ids:
        if step_id in seen:
            continue
        seen.add(step_id)
        unique_step_ids.append(step_id)
    return unique_step_ids


def _compute_model_human_step_label_hit_rates(
    results_dir: Path,
    model_name: str,
    human_cases: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    if not results_dir.exists():
        return {
            "model": model_name,
            "results_dir": str(results_dir),
            "available": False,
            "reason": "results_dir_not_found",
            "evidence_items_compared": 0,
            "evidence_hits": 0,
            "evidence_human_label_hit_rate": None,
            "step_verdict_items_compared": 0,
            "step_verdict_hits": 0,
            "step_verdict_hit_rate": None,
            "evidence_by_predicted_verdict": {label: {"total": 0, "hit": 0, "hit_rate": None} for label in SUPPORTED_LABELS},
            "step_verdict_by_predicted_verdict": {label: {"total": 0, "hit": 0, "hit_rate": None} for label in SUPPORTED_LABELS},
        }

    evidence_total = 0
    evidence_hits = 0
    step_total = 0
    step_hits = 0

    evidence_by_verdict = {label: {"total": 0, "hit": 0} for label in SUPPORTED_LABELS}
    step_by_verdict = {label: {"total": 0, "hit": 0} for label in SUPPORTED_LABELS}

    human_cases_covered = 0

    for json_file in sorted(results_dir.rglob("*__evaluated.json")):
        if not json_file.is_file():
            continue
        try:
            record = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(record, dict):
            continue

        data_id = str(record.get("data_id") or "").strip()
        if not data_id:
            continue

        human_case = human_cases.get(data_id)
        if not isinstance(human_case, dict):
            continue

        human_step_labels = human_case.get("step_labels")
        if not isinstance(human_step_labels, dict) or not human_step_labels:
            continue

        criteria1_result = _extract_criteria1_result(record)
        if not isinstance(criteria1_result, dict):
            continue

        involved_steps = criteria1_result.get("involved_steps")
        if not isinstance(involved_steps, list):
            continue

        human_cases_covered += 1

        predicted_step_verdicts: Dict[int, str] = {}

        for phase in involved_steps:
            if not isinstance(phase, dict):
                continue

            phase_verdict = _normalize_label(phase.get("evaluateStatus"))

            phase_steps = phase.get("steps")
            if phase_verdict is not None and isinstance(phase_steps, list):
                for raw_phase_step in phase_steps:
                    for step_id in _resolve_step_id_candidates_from_record(record, raw_phase_step):
                        if step_id not in human_step_labels:
                            continue
                        if step_id not in predicted_step_verdicts:
                            predicted_step_verdicts[step_id] = phase_verdict

            highlighted = phase.get("highlighted_evidence")
            if not isinstance(highlighted, list):
                continue

            for item in highlighted:
                if not isinstance(item, dict):
                    continue
                evidence_verdict = _normalize_label(item.get("verdict"))
                if evidence_verdict is None:
                    continue

                candidate_step_ids = _resolve_step_id_candidates_from_record(record, item.get("step_index"))
                candidate_human_labels = [human_step_labels[step_id] for step_id in candidate_step_ids if step_id in human_step_labels]
                if not candidate_human_labels:
                    continue

                evidence_total += 1
                evidence_by_verdict[evidence_verdict]["total"] += 1
                if evidence_verdict in candidate_human_labels:
                    evidence_hits += 1
                    evidence_by_verdict[evidence_verdict]["hit"] += 1

        for step_id, predicted_verdict in predicted_step_verdicts.items():
            if predicted_verdict not in step_by_verdict:
                continue

            human_verdict = _normalize_label(human_step_labels.get(step_id))
            if human_verdict is None:
                continue

            step_total += 1
            step_by_verdict[predicted_verdict]["total"] += 1
            if predicted_verdict == human_verdict:
                step_hits += 1
                step_by_verdict[predicted_verdict]["hit"] += 1

    evidence_by_predicted_verdict = {
        label: {
            "total": evidence_by_verdict[label]["total"],
            "hit": evidence_by_verdict[label]["hit"],
            "hit_rate": (
                evidence_by_verdict[label]["hit"] / evidence_by_verdict[label]["total"]
                if evidence_by_verdict[label]["total"] > 0
                else None
            ),
        }
        for label in SUPPORTED_LABELS
    }

    step_verdict_by_predicted_verdict = {
        label: {
            "total": step_by_verdict[label]["total"],
            "hit": step_by_verdict[label]["hit"],
            "hit_rate": (
                step_by_verdict[label]["hit"] / step_by_verdict[label]["total"]
                if step_by_verdict[label]["total"] > 0
                else None
            ),
        }
        for label in SUPPORTED_LABELS
    }

    return {
        "model": model_name,
        "results_dir": str(results_dir),
        "available": True,
        "human_cases_covered": human_cases_covered,
        "evidence_items_compared": evidence_total,
        "evidence_hits": evidence_hits,
        "evidence_human_label_hit_rate": (evidence_hits / evidence_total) if evidence_total > 0 else None,
        "step_verdict_items_compared": step_total,
        "step_verdict_hits": step_hits,
        "step_verdict_hit_rate": (step_hits / step_total) if step_total > 0 else None,
        "evidence_by_predicted_verdict": evidence_by_predicted_verdict,
        "step_verdict_by_predicted_verdict": step_verdict_by_predicted_verdict,
    }


def _build_model_vs_human_metrics(
    model_labels: Dict[str, str],
    human_labels: Dict[str, str],
    label_space: Sequence[str],
    model_distribution_key: str,
) -> Dict[str, Any]:
    common_ids = sorted(set(human_labels.keys()) & set(model_labels.keys()))
    human_eval = [human_labels[data_id] for data_id in common_ids]
    model_eval = [model_labels[data_id] for data_id in common_ids]

    return {
        "sample_size": len(common_ids),
        "accuracy": _accuracy(human_eval, model_eval),
        "macro_f1": _macro_f1(human_eval, model_eval, label_space),
        "cohens_kappa": _cohens_kappa(human_eval, model_eval, label_space),
        "human_distribution": _label_distribution(human_eval, label_space),
        model_distribution_key: _label_distribution(model_eval, label_space),
        "confusion_matrix": _confusion_matrix(human_eval, model_eval, label_space),
    }


def _build_disagreement_cases(
    common_ids: Sequence[str],
    left_cases: Dict[str, Dict[str, Any]],
    right_cases: Dict[str, Dict[str, Any]],
    left_name: str,
    right_name: str,
) -> List[Dict[str, Any]]:
    disagreements: List[Dict[str, Any]] = []
    for data_id in common_ids:
        left = left_cases.get(data_id)
        right = right_cases.get(data_id)
        if not isinstance(left, dict) or not isinstance(right, dict):
            continue

        left_label = _normalize_label(left.get("overall_assessment"))
        right_label = _normalize_label(right.get("overall_assessment"))
        if left_label is None or right_label is None:
            continue
        if left_label == right_label:
            continue

        case = {
            "data_id": data_id,
            f"{left_name}_overall_assessment": left_label,
            f"{right_name}_overall_assessment": right_label,
            f"{left_name}_overall_reasoning": left.get("overall_reasoning"),
            f"{right_name}_overall_reasoning": right.get("overall_reasoning"),
            f"{left_name}_evidence": left.get("evidence") if isinstance(left.get("evidence"), list) else [],
            f"{right_name}_evidence": right.get("evidence") if isinstance(right.get("evidence"), list) else [],
        }

        left_source_file = left.get("source_file")
        if isinstance(left_source_file, str) and left_source_file.strip():
            case[f"{left_name}_source_file"] = left_source_file

        right_source_file = right.get("source_file")
        if isinstance(right_source_file, str) and right_source_file.strip():
            case[f"{right_name}_source_file"] = right_source_file

        disagreements.append(case)

    return disagreements


def compute_metrics(
    gpt_cases: Dict[str, Dict[str, Any]],
    deepseek_cases: Dict[str, Dict[str, Any]],
    baseline_gpt_cases: Dict[str, Dict[str, Any]],
    baseline_deepseek_cases: Dict[str, Dict[str, Any]],
    human_cases: Dict[str, Dict[str, Any]],
    fixed_ground_truth_cases: Dict[str, Dict[str, Any]],
    gpt_dir: Path,
    deepseek_dir: Path,
    baseline_gpt_dir: Path,
    baseline_deepseek_dir: Path,
    gpt_evidence_accuracy: Dict[str, Any],
    deepseek_evidence_accuracy: Dict[str, Any],
    baseline_gpt_evidence_accuracy: Dict[str, Any],
    baseline_deepseek_evidence_accuracy: Dict[str, Any],
    gpt_vs_human_step_hit: Dict[str, Any],
    deepseek_vs_human_step_hit: Dict[str, Any],
    baseline_gpt_vs_human_step_hit: Dict[str, Any],
    baseline_deepseek_vs_human_step_hit: Dict[str, Any],
    human_file: Path,
    fixed_ground_truth_file: Path,
) -> Dict[str, Any]:
    label_space = list(SUPPORTED_LABELS)

    gpt_labels = {
        data_id: str(case["overall_assessment"])
        for data_id, case in gpt_cases.items()
        if "overall_assessment" in case
    }
    deepseek_labels = {
        data_id: str(case["overall_assessment"])
        for data_id, case in deepseek_cases.items()
        if "overall_assessment" in case
    }
    baseline_gpt_labels = {
        data_id: str(case["overall_assessment"])
        for data_id, case in baseline_gpt_cases.items()
        if "overall_assessment" in case
    }
    baseline_deepseek_labels = {
        data_id: str(case["overall_assessment"])
        for data_id, case in baseline_deepseek_cases.items()
        if "overall_assessment" in case
    }
    human_labels = {
        data_id: str(case["overall_assessment"])
        for data_id, case in human_cases.items()
        if "overall_assessment" in case
    }

    common_model_ids = sorted(set(gpt_labels.keys()) & set(deepseek_labels.keys()))
    gpt_common = [gpt_labels[data_id] for data_id in common_model_ids]
    deepseek_common = [deepseek_labels[data_id] for data_id in common_model_ids]

    model_agreement = {
        "sample_size": len(common_model_ids),
        "agreement_rate": _accuracy(gpt_common, deepseek_common),
        "cohens_kappa": _cohens_kappa(gpt_common, deepseek_common, label_space),
        "gpt5_distribution": _label_distribution(gpt_common, label_space),
        "deepseek_distribution": _label_distribution(deepseek_common, label_space),
        "confusion_matrix": _confusion_matrix(gpt_common, deepseek_common, label_space),
    }

    gpt_vs_human = _build_model_vs_human_metrics(
        model_labels=gpt_labels,
        human_labels=human_labels,
        label_space=label_space,
        model_distribution_key="gpt5_distribution",
    )
    deepseek_vs_human = _build_model_vs_human_metrics(
        model_labels=deepseek_labels,
        human_labels=human_labels,
        label_space=label_space,
        model_distribution_key="deepseek_distribution",
    )
    baseline_gpt_vs_human = _build_model_vs_human_metrics(
        model_labels=baseline_gpt_labels,
        human_labels=human_labels,
        label_space=label_space,
        model_distribution_key="baseline_gpt5_distribution",
    )
    baseline_deepseek_vs_human = _build_model_vs_human_metrics(
        model_labels=baseline_deepseek_labels,
        human_labels=human_labels,
        label_space=label_space,
        model_distribution_key="baseline_deepseek_distribution",
    )

    gpt_vs_fixed_ground_truth = _build_fixed_ground_truth_metrics(
        model_cases=gpt_cases,
        fixed_ground_truth_cases=fixed_ground_truth_cases,
        label_space=label_space,
        model_name="gpt5",
        model_distribution_key="gpt5_distribution",
    )
    deepseek_vs_fixed_ground_truth = _build_fixed_ground_truth_metrics(
        model_cases=deepseek_cases,
        fixed_ground_truth_cases=fixed_ground_truth_cases,
        label_space=label_space,
        model_name="deepseek",
        model_distribution_key="deepseek_distribution",
    )
    baseline_gpt_vs_fixed_ground_truth = _build_fixed_ground_truth_metrics(
        model_cases=baseline_gpt_cases,
        fixed_ground_truth_cases=fixed_ground_truth_cases,
        label_space=label_space,
        model_name="baseline_gpt5",
        model_distribution_key="baseline_gpt5_distribution",
    )
    baseline_deepseek_vs_fixed_ground_truth = _build_fixed_ground_truth_metrics(
        model_cases=baseline_deepseek_cases,
        fixed_ground_truth_cases=fixed_ground_truth_cases,
        label_space=label_space,
        model_name="baseline_deepseek",
        model_distribution_key="baseline_deepseek_distribution",
    )

    common_human_gpt_ids = sorted(set(human_labels.keys()) & set(gpt_labels.keys()))
    common_human_deepseek_ids = sorted(set(human_labels.keys()) & set(deepseek_labels.keys()))
    common_human_baseline_gpt_ids = sorted(set(human_labels.keys()) & set(baseline_gpt_labels.keys()))
    common_human_baseline_deepseek_ids = sorted(set(human_labels.keys()) & set(baseline_deepseek_labels.keys()))

    gpt_vs_deepseek_disagreements = _build_disagreement_cases(
        common_ids=common_model_ids,
        left_cases=gpt_cases,
        right_cases=deepseek_cases,
        left_name="gpt5",
        right_name="deepseek",
    )
    gpt_vs_human_disagreements = _build_disagreement_cases(
        common_ids=common_human_gpt_ids,
        left_cases=gpt_cases,
        right_cases=human_cases,
        left_name="gpt5",
        right_name="human",
    )
    deepseek_vs_human_disagreements = _build_disagreement_cases(
        common_ids=common_human_deepseek_ids,
        left_cases=deepseek_cases,
        right_cases=human_cases,
        left_name="deepseek",
        right_name="human",
    )
    baseline_gpt_vs_human_disagreements = _build_disagreement_cases(
        common_ids=common_human_baseline_gpt_ids,
        left_cases=baseline_gpt_cases,
        right_cases=human_cases,
        left_name="baseline_gpt5",
        right_name="human",
    )
    baseline_deepseek_vs_human_disagreements = _build_disagreement_cases(
        common_ids=common_human_baseline_deepseek_ids,
        left_cases=baseline_deepseek_cases,
        right_cases=human_cases,
        left_name="baseline_deepseek",
        right_name="human",
    )

    return {
        "task": "criteria1 agreement and human accuracy",
        "labels": label_space,
        "sources": {
            "gpt_dir": str(gpt_dir),
            "deepseek_dir": str(deepseek_dir),
            "baseline_gpt_dir": str(baseline_gpt_dir),
            "baseline_deepseek_dir": str(baseline_deepseek_dir),
            "human_file": str(human_file),
            "fixed_ground_truth_file": str(fixed_ground_truth_file),
        },
        "record_counts": {
            "gpt5_records": len(gpt_labels),
            "deepseek_records": len(deepseek_labels),
            "baseline_gpt5_records": len(baseline_gpt_labels),
            "baseline_deepseek_records": len(baseline_deepseek_labels),
            "human_records": len(human_labels),
            "fixed_ground_truth_records": len(fixed_ground_truth_cases),
        },
        "gpt5_vs_deepseek": model_agreement,
        "gpt5_vs_human": gpt_vs_human,
        "deepseek_vs_human": deepseek_vs_human,
        "baseline_gpt5_vs_human": baseline_gpt_vs_human,
        "baseline_deepseek_vs_human": baseline_deepseek_vs_human,
        "fixed_ground_truth_accuracy": {
            "mapping": FIXED_GROUND_TRUTH_BUCKET_TO_LABEL,
            "excluded_buckets": ["controversial"],
            "gpt5": gpt_vs_fixed_ground_truth,
            "deepseek": deepseek_vs_fixed_ground_truth,
            "baseline_gpt5": baseline_gpt_vs_fixed_ground_truth,
            "baseline_deepseek": baseline_deepseek_vs_fixed_ground_truth,
        },
        "evidence_substring_accuracy": {
            "gpt5": gpt_evidence_accuracy,
            "deepseek": deepseek_evidence_accuracy,
            "baseline_gpt5": baseline_gpt_evidence_accuracy,
            "baseline_deepseek": baseline_deepseek_evidence_accuracy,
        },
        "baseline_evidence_substring_accuracy": {
            "baseline_gpt5": baseline_gpt_evidence_accuracy,
            "baseline_deepseek": baseline_deepseek_evidence_accuracy,
        },
        "evidence_vs_human_label_hit_rate": {
            "gpt5": gpt_vs_human_step_hit,
            "deepseek": deepseek_vs_human_step_hit,
            "baseline_gpt5": baseline_gpt_vs_human_step_hit,
            "baseline_deepseek": baseline_deepseek_vs_human_step_hit,
        },
        "disagreement_counts": {
            "gpt5_vs_deepseek_overall_assessment_diff": len(gpt_vs_deepseek_disagreements),
            "gpt5_vs_human_overall_assessment_diff": len(gpt_vs_human_disagreements),
            "deepseek_vs_human_overall_assessment_diff": len(deepseek_vs_human_disagreements),
            "baseline_gpt5_vs_human_overall_assessment_diff": len(baseline_gpt_vs_human_disagreements),
            "baseline_deepseek_vs_human_overall_assessment_diff": len(baseline_deepseek_vs_human_disagreements),
        },
        "disagreement_cases": {
            "gpt5_vs_deepseek_overall_assessment_diff": gpt_vs_deepseek_disagreements,
            "gpt5_vs_human_overall_assessment_diff": gpt_vs_human_disagreements,
            "deepseek_vs_human_overall_assessment_diff": deepseek_vs_human_disagreements,
            "baseline_gpt5_vs_human_overall_assessment_diff": baseline_gpt_vs_human_disagreements,
            "baseline_deepseek_vs_human_overall_assessment_diff": baseline_deepseek_vs_human_disagreements,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute criteria1 inter-model agreement and model-vs-human accuracy metrics."
    )
    parser.add_argument("--gpt-dir", default=str(DEFAULT_GPT_DIR), help="Directory of GPT evaluated JSON files")
    parser.add_argument("--deepseek-dir", default=str(DEFAULT_DEEPSEEK_DIR), help="Directory of Deepseek evaluated JSON files")
    parser.add_argument(
        "--baseline-gpt-dir",
        default=str(DEFAULT_BASELINE_GPT_DIR),
        help="Directory of baseline GPT evaluated JSON files",
    )
    parser.add_argument(
        "--baseline-deepseek-dir",
        default=str(DEFAULT_BASELINE_DEEPSEEK_DIR),
        help="Directory of baseline Deepseek evaluated JSON files",
    )
    parser.add_argument(
        "--human-file",
        default=str(DEFAULT_HUMAN_FILE),
        help="Human annotation JSON (Yukun_criteria1_annotations.json format)",
    )
    parser.add_argument(
        "--fixed-ground-truth-file",
        default=str(DEFAULT_FIXED_GROUND_TRUTH_FILE),
        help="Persona redesign preview JSON used as fixed ground truth (satisfy=pass, not_satisfy=fail, controversial skipped)",
    )
    parser.add_argument(
        "--output-file",
        default=str(DEFAULT_OUTPUT_FILE),
        help="Output JSON file path for computed metrics",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    gpt_dir = Path(args.gpt_dir).resolve()
    deepseek_dir = Path(args.deepseek_dir).resolve()
    baseline_gpt_dir = Path(args.baseline_gpt_dir).resolve()
    baseline_deepseek_dir = Path(args.baseline_deepseek_dir).resolve()
    human_file = Path(args.human_file).resolve()
    fixed_ground_truth_file = Path(args.fixed_ground_truth_file).resolve()
    output_file = Path(args.output_file).resolve()

    if not gpt_dir.exists():
        raise FileNotFoundError(f"GPT results dir not found: {gpt_dir}")
    if not deepseek_dir.exists():
        raise FileNotFoundError(f"Deepseek results dir not found: {deepseek_dir}")
    if not human_file.exists():
        raise FileNotFoundError(f"Human annotation file not found: {human_file}")

    if not baseline_gpt_dir.exists():
        print(f"[WARN] Baseline GPT results dir not found: {baseline_gpt_dir}")
    if not baseline_deepseek_dir.exists():
        print(f"[WARN] Baseline Deepseek results dir not found: {baseline_deepseek_dir}")
    if not fixed_ground_truth_file.exists():
        print(f"[WARN] Fixed ground truth file not found: {fixed_ground_truth_file}")

    gpt_cases = _load_model_cases(gpt_dir)
    deepseek_cases = _load_model_cases(deepseek_dir)
    baseline_gpt_cases = _load_model_cases(baseline_gpt_dir) if baseline_gpt_dir.exists() else {}
    baseline_deepseek_cases = _load_model_cases(baseline_deepseek_dir) if baseline_deepseek_dir.exists() else {}
    human_cases = _load_human_cases(human_file)
    fixed_ground_truth_cases = (
        _load_fixed_ground_truth_cases(fixed_ground_truth_file)
        if fixed_ground_truth_file.exists()
        else {}
    )

    gpt_evidence_accuracy = _compute_evidence_substring_accuracy(
        results_dir=gpt_dir,
        model_name="gpt5",
    )
    deepseek_evidence_accuracy = _compute_evidence_substring_accuracy(
        results_dir=deepseek_dir,
        model_name="deepseek",
    )
    baseline_gpt_evidence_accuracy = _compute_evidence_substring_accuracy(
        results_dir=baseline_gpt_dir,
        model_name="baseline_gpt5",
    )
    baseline_deepseek_evidence_accuracy = _compute_evidence_substring_accuracy(
        results_dir=baseline_deepseek_dir,
        model_name="baseline_deepseek",
    )
    gpt_vs_human_step_hit = _compute_model_human_step_label_hit_rates(
        results_dir=gpt_dir,
        model_name="gpt5",
        human_cases=human_cases,
    )
    deepseek_vs_human_step_hit = _compute_model_human_step_label_hit_rates(
        results_dir=deepseek_dir,
        model_name="deepseek",
        human_cases=human_cases,
    )
    baseline_gpt_vs_human_step_hit = _compute_model_human_step_label_hit_rates(
        results_dir=baseline_gpt_dir,
        model_name="baseline_gpt5",
        human_cases=human_cases,
    )
    baseline_deepseek_vs_human_step_hit = _compute_model_human_step_label_hit_rates(
        results_dir=baseline_deepseek_dir,
        model_name="baseline_deepseek",
        human_cases=human_cases,
    )

    report = compute_metrics(
        gpt_cases=gpt_cases,
        deepseek_cases=deepseek_cases,
        baseline_gpt_cases=baseline_gpt_cases,
        baseline_deepseek_cases=baseline_deepseek_cases,
        human_cases=human_cases,
        fixed_ground_truth_cases=fixed_ground_truth_cases,
        gpt_dir=gpt_dir,
        deepseek_dir=deepseek_dir,
        baseline_gpt_dir=baseline_gpt_dir,
        baseline_deepseek_dir=baseline_deepseek_dir,
        gpt_evidence_accuracy=gpt_evidence_accuracy,
        deepseek_evidence_accuracy=deepseek_evidence_accuracy,
        baseline_gpt_evidence_accuracy=baseline_gpt_evidence_accuracy,
        baseline_deepseek_evidence_accuracy=baseline_deepseek_evidence_accuracy,
        gpt_vs_human_step_hit=gpt_vs_human_step_hit,
        deepseek_vs_human_step_hit=deepseek_vs_human_step_hit,
        baseline_gpt_vs_human_step_hit=baseline_gpt_vs_human_step_hit,
        baseline_deepseek_vs_human_step_hit=baseline_deepseek_vs_human_step_hit,
        human_file=human_file,
        fixed_ground_truth_file=fixed_ground_truth_file,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[DONE] Wrote metrics report: {output_file}")
    print(
        "[SUMMARY] gpt5_vs_deepseek: n={} agreement_rate={} kappa={}".format(
            report["gpt5_vs_deepseek"]["sample_size"],
            report["gpt5_vs_deepseek"]["agreement_rate"],
            report["gpt5_vs_deepseek"]["cohens_kappa"],
        )
    )
    print(
        "[SUMMARY] gpt5_vs_human: n={} accuracy={} macro_f1={} kappa={}".format(
            report["gpt5_vs_human"]["sample_size"],
            report["gpt5_vs_human"]["accuracy"],
            report["gpt5_vs_human"]["macro_f1"],
            report["gpt5_vs_human"]["cohens_kappa"],
        )
    )
    print(
        "[SUMMARY] deepseek_vs_human: n={} accuracy={} macro_f1={} kappa={}".format(
            report["deepseek_vs_human"]["sample_size"],
            report["deepseek_vs_human"]["accuracy"],
            report["deepseek_vs_human"]["macro_f1"],
            report["deepseek_vs_human"]["cohens_kappa"],
        )
    )
    print(
        "[SUMMARY] baseline_gpt5_vs_human: n={} accuracy={} macro_f1={} kappa={}".format(
            report["baseline_gpt5_vs_human"]["sample_size"],
            report["baseline_gpt5_vs_human"]["accuracy"],
            report["baseline_gpt5_vs_human"]["macro_f1"],
            report["baseline_gpt5_vs_human"]["cohens_kappa"],
        )
    )
    print(
        "[SUMMARY] baseline_deepseek_vs_human: n={} accuracy={} macro_f1={} kappa={}".format(
            report["baseline_deepseek_vs_human"]["sample_size"],
            report["baseline_deepseek_vs_human"]["accuracy"],
            report["baseline_deepseek_vs_human"]["macro_f1"],
            report["baseline_deepseek_vs_human"]["cohens_kappa"],
        )
    )
    print(
        "[SUMMARY] fixed_ground_truth gpt5: covered={}/{} accuracy={}".format(
            report["fixed_ground_truth_accuracy"]["gpt5"]["covered_cases"],
            report["fixed_ground_truth_accuracy"]["gpt5"]["fixed_ground_truth_total"],
            report["fixed_ground_truth_accuracy"]["gpt5"]["accuracy"],
        )
    )
    print(
        "[SUMMARY] fixed_ground_truth deepseek: covered={}/{} accuracy={}".format(
            report["fixed_ground_truth_accuracy"]["deepseek"]["covered_cases"],
            report["fixed_ground_truth_accuracy"]["deepseek"]["fixed_ground_truth_total"],
            report["fixed_ground_truth_accuracy"]["deepseek"]["accuracy"],
        )
    )
    print(
        "[SUMMARY] fixed_ground_truth baseline_gpt5: covered={}/{} accuracy={}".format(
            report["fixed_ground_truth_accuracy"]["baseline_gpt5"]["covered_cases"],
            report["fixed_ground_truth_accuracy"]["baseline_gpt5"]["fixed_ground_truth_total"],
            report["fixed_ground_truth_accuracy"]["baseline_gpt5"]["accuracy"],
        )
    )
    print(
        "[SUMMARY] fixed_ground_truth baseline_deepseek: covered={}/{} accuracy={}".format(
            report["fixed_ground_truth_accuracy"]["baseline_deepseek"]["covered_cases"],
            report["fixed_ground_truth_accuracy"]["baseline_deepseek"]["fixed_ground_truth_total"],
            report["fixed_ground_truth_accuracy"]["baseline_deepseek"]["accuracy"],
        )
    )
    print(
        "[SUMMARY] gpt5 evidence substring accuracy: items={} grounded={} acc={}".format(
            report["evidence_substring_accuracy"]["gpt5"]["evidence_items_total"],
            report["evidence_substring_accuracy"]["gpt5"]["substring_grounded_items"],
            report["evidence_substring_accuracy"]["gpt5"]["substring_grounding_accuracy"],
        )
    )
    print(
        "[SUMMARY] deepseek evidence substring accuracy: items={} grounded={} acc={}".format(
            report["evidence_substring_accuracy"]["deepseek"]["evidence_items_total"],
            report["evidence_substring_accuracy"]["deepseek"]["substring_grounded_items"],
            report["evidence_substring_accuracy"]["deepseek"]["substring_grounding_accuracy"],
        )
    )
    print(
        "[SUMMARY] baseline_gpt5 evidence substring accuracy: items={} grounded={} acc={}".format(
            report["evidence_substring_accuracy"]["baseline_gpt5"]["evidence_items_total"],
            report["evidence_substring_accuracy"]["baseline_gpt5"]["substring_grounded_items"],
            report["evidence_substring_accuracy"]["baseline_gpt5"]["substring_grounding_accuracy"],
        )
    )
    print(
        "[SUMMARY] baseline_deepseek evidence substring accuracy: items={} grounded={} acc={}".format(
            report["evidence_substring_accuracy"]["baseline_deepseek"]["evidence_items_total"],
            report["evidence_substring_accuracy"]["baseline_deepseek"]["substring_grounded_items"],
            report["evidence_substring_accuracy"]["baseline_deepseek"]["substring_grounding_accuracy"],
        )
    )
    print(
        "[SUMMARY] gpt5 evidence-vs-human hit_rate={} | step_verdict_hit_rate={}".format(
            report["evidence_vs_human_label_hit_rate"]["gpt5"]["evidence_human_label_hit_rate"],
            report["evidence_vs_human_label_hit_rate"]["gpt5"]["step_verdict_hit_rate"],
        )
    )
    print(
        "[SUMMARY] deepseek evidence-vs-human hit_rate={} | step_verdict_hit_rate={}".format(
            report["evidence_vs_human_label_hit_rate"]["deepseek"]["evidence_human_label_hit_rate"],
            report["evidence_vs_human_label_hit_rate"]["deepseek"]["step_verdict_hit_rate"],
        )
    )
    print(
        "[SUMMARY] baseline_gpt5 evidence-vs-human hit_rate={} | step_verdict_hit_rate={}".format(
            report["evidence_vs_human_label_hit_rate"]["baseline_gpt5"]["evidence_human_label_hit_rate"],
            report["evidence_vs_human_label_hit_rate"]["baseline_gpt5"]["step_verdict_hit_rate"],
        )
    )
    print(
        "[SUMMARY] baseline_deepseek evidence-vs-human hit_rate={} | step_verdict_hit_rate={}".format(
            report["evidence_vs_human_label_hit_rate"]["baseline_deepseek"]["evidence_human_label_hit_rate"],
            report["evidence_vs_human_label_hit_rate"]["baseline_deepseek"]["step_verdict_hit_rate"],
        )
    )


if __name__ == "__main__":
    main()
