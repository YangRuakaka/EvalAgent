from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
TECH_EVAL_DIR = Path(__file__).resolve().parent


def _strip_wrapping_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1]
    return stripped


def _load_env_file(env_path: Path, override: bool = False) -> int:
    if not env_path.exists() or not env_path.is_file():
        return 0

    loaded = 0
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        if not override and key in os.environ:
            continue

        os.environ[key] = _strip_wrapping_quotes(value)
        loaded += 1

    return loaded


def _bootstrap_env() -> None:
    env_candidates = [
        TECH_EVAL_DIR / ".env",
        BACKEND_DIR / ".env",
        ROOT_DIR / ".env",
    ]

    loaded = 0
    for env_path in env_candidates:
        loaded += _load_env_file(env_path, override=False)

    if loaded > 0:
        print(f"[INFO] Loaded {loaded} env vars from local .env files")


_bootstrap_env()


def _configure_logging() -> None:
    # Ensure backend judge INFO logs are visible when running local batch evaluation.
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s - %(message)s",
        force=True,
    )


_configure_logging()

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.deps import get_judge_services
from app.api.judge import evaluate_experiment
from app.core.config import settings
from app.core.storage_paths import get_condition_lookup_dirs
from app.schemas.judge import ExperimentEvaluationRequest


@dataclass
class RequestParseResult:
    payloads: List[dict[str, Any]]
    warnings: List[str]


@dataclass
class InputSourceRequests:
    source_name: str
    payloads: List[dict[str, Any]]
    warnings: List[str]
    source_path: Path | None = None
    source_json_data: dict[str, Any] | None = None
    source_criteria_mapping: list[dict[str, str]] | None = None


DEFAULT_DATASET_JSON_CRITERIA: list[dict[str, str]] = [
    {
        "title": "Task Completion",
        "assertion": "The agent completes the assigned user task successfully and reaches the intended end state.",
        "description": "Judge completion quality using execution trace, final result, and consistency of actions.",
    }
]


def _safe_filename_token(raw: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw or "").strip())
    token = token.strip("-._")
    return token or "model"


def _normalize_model_overrides(models: Sequence[str] | None) -> list[str]:
    normalized: list[str] = []
    if not models:
        return normalized

    for model in models:
        for item in str(model or "").split(","):
            candidate = item.strip()
            if candidate and candidate not in normalized:
                normalized.append(candidate)

    return normalized


def _extract_json_code_blocks(text: str) -> list[str]:
    pattern = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
    return [match.strip() for match in pattern.findall(text) if match.strip()]


def _decode_json_objects_from_text(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    objects: list[Any] = []
    idx = 0
    length = len(text)

    while idx < length:
        if text[idx] not in "[{":
            idx += 1
            continue

        try:
            obj, consumed = decoder.raw_decode(text[idx:])
            objects.append(obj)
            idx += consumed
        except json.JSONDecodeError:
            idx += 1

    return objects


def _is_experiment_payload(data: Any) -> bool:
    return isinstance(data, dict) and "conditions" in data and "criteria" in data


def _normalize_conditions(raw_conditions: Any) -> list[dict[str, str]]:
    if not isinstance(raw_conditions, list):
        raise ValueError("`conditions` must be a list")

    normalized: list[dict[str, str]] = []
    for item in raw_conditions:
        if isinstance(item, str) and item.strip():
            normalized.append({"conditionID": item.strip()})
            continue

        if isinstance(item, dict):
            condition_id = item.get("conditionID") or item.get("id") or item.get("name")
            if isinstance(condition_id, str) and condition_id.strip():
                normalized.append({"conditionID": condition_id.strip()})
                continue

        raise ValueError(f"Unrecognized condition: {item}")

    return normalized


def _normalize_criteria(raw_criteria: Any) -> list[dict[str, str]]:
    if not isinstance(raw_criteria, list):
        raise ValueError("`criteria` must be a list")

    normalized: list[dict[str, str]] = []
    for item in raw_criteria:
        if not isinstance(item, dict):
            raise ValueError(f"Unrecognized criterion: {item}")

        title = item.get("title") or item.get("name")
        assertion = item.get("assertion") or item.get("claim")
        description = item.get("description")

        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"criterion missing title/name: {item}")
        if not isinstance(assertion, str) or not assertion.strip():
            raise ValueError(f"criterion missing assertion/claim: {item}")

        normalized_item: dict[str, str] = {
            "title": title.strip(),
            "assertion": assertion.strip(),
        }
        if isinstance(description, str) and description.strip():
            normalized_item["description"] = description.strip()

        normalized.append(normalized_item)

    return normalized


def _coerce_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "conditions": _normalize_conditions(payload.get("conditions")),
        "criteria": _normalize_criteria(payload.get("criteria")),
    }

    judge_model = payload.get("judge_model")
    if isinstance(judge_model, str) and judge_model.strip():
        normalized["judge_model"] = judge_model.strip()

    forced_granularity = payload.get("forced_granularity")
    if isinstance(forced_granularity, str) and forced_granularity.strip():
        normalized["forced_granularity"] = forced_granularity.strip()

    return normalized


def _iter_possible_payloads(parsed_obj: Any) -> Iterable[dict[str, Any]]:
    if _is_experiment_payload(parsed_obj):
        yield parsed_obj
        return

    if isinstance(parsed_obj, list):
        for item in parsed_obj:
            if _is_experiment_payload(item):
                yield item
        return

    if isinstance(parsed_obj, dict):
        requests = parsed_obj.get("requests")
        if isinstance(requests, list):
            for item in requests:
                if _is_experiment_payload(item):
                    yield item


def parse_requests_from_txt(txt_path: Path) -> RequestParseResult:
    content = txt_path.read_text(encoding="utf-8")
    warnings: list[str] = []
    parsed_candidates: list[Any] = []

    blocks = _extract_json_code_blocks(content)
    for block in blocks:
        try:
            parsed_candidates.append(json.loads(block))
        except json.JSONDecodeError as exc:
            warnings.append(f"Code block JSON parse failed: {exc}")

    if not blocks:
        try:
            parsed_candidates.append(json.loads(content))
        except json.JSONDecodeError:
            pass

    parsed_candidates.extend(_decode_json_objects_from_text(content))

    payloads: list[dict[str, Any]] = []
    for candidate in parsed_candidates:
        for payload in _iter_possible_payloads(candidate):
            try:
                payloads.append(_coerce_payload(payload))
            except Exception as exc:
                warnings.append(f"Found candidate request but normalization failed: {exc}")

    unique_payloads: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for payload in payloads:
        key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_payloads.append(payload)

    return RequestParseResult(payloads=unique_payloads, warnings=warnings)


def _load_criteria_from_file(criteria_file: Path) -> list[dict[str, str]]:
    if not criteria_file.exists() or not criteria_file.is_file():
        raise ValueError(f"criteria file does not exist: {criteria_file}")

    parsed = json.loads(criteria_file.read_text(encoding="utf-8"))
    raw_criteria: Any

    if isinstance(parsed, list):
        raw_criteria = parsed
    elif isinstance(parsed, dict):
        if isinstance(parsed.get("criteria"), list):
            raw_criteria = parsed.get("criteria")
        else:
            raise ValueError("criteria file JSON object must include a `criteria` list")
    else:
        raise ValueError("criteria file must be a JSON list or an object containing `criteria`")

    normalized = _normalize_criteria(raw_criteria)
    if not normalized:
        raise ValueError("criteria list is empty after normalization")
    return normalized


def _extract_task_name_and_url(task_raw: str, fallback_name: str) -> tuple[str, str]:
    text = str(task_raw or "").strip()
    if not text:
        return fallback_name, ""

    url_match = re.search(r"https?://\S+", text)
    url = url_match.group(0).rstrip(".,)") if url_match else ""

    if " from " in text.lower():
        split_index = text.lower().find(" from ")
        candidate_name = text[:split_index].strip()
        if candidate_name:
            return candidate_name, url

    return text, url


def _infer_value_from_persona(persona: str) -> str | None:
    text = str(persona or "")
    match = re.search(r"values?\s+([A-Za-z][A-Za-z_-]*)", text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip().lower()


def _criterion_sort_key(raw_key: str) -> tuple[int, str]:
    match = re.fullmatch(r"criteria(\d+)", str(raw_key).strip(), re.IGNORECASE)
    if match:
        return (int(match.group(1)), str(raw_key))
    return (10_000, str(raw_key))


def _extract_criteria_from_dataset_json(source_json: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    warnings: list[str] = []
    normalized_criteria: list[dict[str, str]] = []
    source_mapping: list[dict[str, str]] = []

    criteria_keys = [
        str(key)
        for key in source_json.keys()
        if re.fullmatch(r"criteria\d+", str(key).strip(), re.IGNORECASE)
    ]
    criteria_keys = sorted(criteria_keys, key=_criterion_sort_key)

    for key in criteria_keys:
        raw_value = source_json.get(key)
        assertion = str(raw_value or "").strip()
        if not assertion:
            continue

        criterion = {
            "title": key,
            "assertion": assertion,
            "description": f"Derived from source dataset field `{key}`.",
        }
        normalized_criteria.append(criterion)
        source_mapping.append(
            {
                "source_key": key,
                "title": criterion["title"],
                "assertion": criterion["assertion"],
            }
        )

    if normalized_criteria:
        return normalized_criteria, source_mapping, warnings

    raw_criteria_list = source_json.get("criteria")
    if isinstance(raw_criteria_list, list):
        try:
            normalized = _normalize_criteria(raw_criteria_list)
            for idx, criterion in enumerate(normalized, start=1):
                normalized_criteria.append(criterion)
                source_mapping.append(
                    {
                        "source_key": f"criteria{idx}",
                        "title": criterion["title"],
                        "assertion": criterion["assertion"],
                    }
                )
            return normalized_criteria, source_mapping, warnings
        except Exception as exc:
            warnings.append(f"failed to parse `criteria` list in source json: {exc}")

    warnings.append("no usable criteria fields found in source json; using default Task Completion criterion")
    return copy.deepcopy(DEFAULT_DATASET_JSON_CRITERIA), [{
        "source_key": "criteria1",
        "title": DEFAULT_DATASET_JSON_CRITERIA[0]["title"],
        "assertion": DEFAULT_DATASET_JSON_CRITERIA[0]["assertion"],
    }], warnings


def _normalize_dataset_json_run_file(
    source_json_path: Path,
    source_json_data: dict[str, Any],
    normalized_json_path: Path,
) -> list[str]:
    warnings: list[str] = []
    parsed = source_json_data

    if not isinstance(parsed, dict):
        raise ValueError("dataset json must be an object")

    fallback_task_name = source_json_path.stem
    task_name, task_url = _extract_task_name_and_url(str(parsed.get("task") or ""), fallback_task_name)
    persona = str(parsed.get("persona") or "").strip()
    value = _infer_value_from_persona(persona)

    raw_steps = parsed.get("steps")
    if not isinstance(raw_steps, list):
        raw_steps = []
        warnings.append("missing `steps` list in source dataset json")

    model_outputs: list[dict[str, Any]] = []
    for step in raw_steps:
        if not isinstance(step, dict):
            continue

        reasoning = str(step.get("AI REASONING") or step.get("thinking") or step.get("thinking_process") or "")
        evaluation = str(step.get("EVALUATION") or step.get("evaluation_previous_goal") or "")
        memory = str(step.get("MEMORY") or step.get("memory") or "")
        next_goal = str(step.get("TARGET OBJECTIVE") or step.get("next_goal") or "")
        action = step.get("ACTION") if "ACTION" in step else step.get("action")

        model_outputs.append(
            {
                "thinking_process": reasoning,
                "thinking": reasoning,
                "evaluation_previous_goal": evaluation,
                "memory": memory,
                "next_goal": next_goal,
                "action": action,
            }
        )

    if not model_outputs:
        warnings.append("no valid steps converted into details.model_outputs")

    run_payload = {
        "metadata": {
            "timestamp_utc": datetime.now().isoformat(),
            "task": {
                "name": task_name,
                "url": task_url,
            },
            "persona": persona,
            "model": str(parsed.get("model") or ""),
            "value": value,
            "run_index": 1,
            "id": source_json_path.stem,
        },
        "summary": {
            "is_done": bool(model_outputs),
            "is_successful": bool(model_outputs),
            "has_errors": False,
            "number_of_steps": len(model_outputs),
            "total_duration_seconds": None,
            "final_result": str(parsed.get("final_result") or ""),
            "error_message": None,
        },
        "details": {
            "screenshots": [],
            "model_outputs": model_outputs,
            "last_action": model_outputs[-1].get("action") if model_outputs else None,
            "structured_output": None,
        },
    }

    normalized_json_path.write_text(
        json.dumps(run_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return warnings


def _build_dataset_json_appended_output(
    source_json_data: dict[str, Any],
    source_file: str,
    request_payload: dict[str, Any],
    llm_output: dict[str, Any],
    source_criteria_mapping: list[dict[str, str]] | None,
    output_file: str,
) -> dict[str, Any]:
    output_payload: dict[str, Any] = copy.deepcopy(source_json_data)

    llm_conditions = llm_output.get("conditions") if isinstance(llm_output, dict) else []
    if not isinstance(llm_conditions, list):
        llm_conditions = []
    primary_condition = llm_conditions[0] if llm_conditions and isinstance(llm_conditions[0], dict) else {}

    llm_criteria = primary_condition.get("criteria") if isinstance(primary_condition, dict) else []
    if not isinstance(llm_criteria, list):
        llm_criteria = []

    llm_criteria_by_title: dict[str, dict[str, Any]] = {}
    for criterion in llm_criteria:
        if not isinstance(criterion, dict):
            continue
        title = str(criterion.get("title") or "").strip()
        if title and title not in llm_criteria_by_title:
            llm_criteria_by_title[title] = criterion

    request_criteria = request_payload.get("criteria") if isinstance(request_payload, dict) else []
    if not isinstance(request_criteria, list):
        request_criteria = []

    criteria_mappings = source_criteria_mapping or []
    criteria_results: list[dict[str, Any]] = []

    for idx, request_criterion in enumerate(request_criteria, start=1):
        if not isinstance(request_criterion, dict):
            continue

        title = str(request_criterion.get("title") or "").strip() or f"criteria{idx}"
        source_key = (
            str(criteria_mappings[idx - 1].get("source_key") or "").strip()
            if idx - 1 < len(criteria_mappings) and isinstance(criteria_mappings[idx - 1], dict)
            else f"criteria{idx}"
        )

        llm_criterion = llm_criteria_by_title.get(title, {})
        criterion_result = {
            "source_key": source_key,
            "title": title,
            "assertion": str(request_criterion.get("assertion") or "").strip(),
            "description": str(request_criterion.get("description") or "").strip(),
            "overall_assessment": llm_criterion.get("overall_assessment"),
            "overall_reasoning": llm_criterion.get("overall_reasoning"),
            "confidence": llm_criterion.get("confidence"),
            "granularity": llm_criterion.get("granularity"),
            "involved_steps": llm_criterion.get("involved_steps") if isinstance(llm_criterion.get("involved_steps"), list) else [],
        }
        criteria_results.append(criterion_result)
        output_payload[f"{source_key}_evaluation"] = criterion_result

    output_payload["judge_evaluation"] = {
        "source_file": source_file,
        "output_file": output_file,
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "judge_model": request_payload.get("judge_model"),
        "condition_id": primary_condition.get("conditionID") if isinstance(primary_condition, dict) else None,
        "multi_condition_assessment": llm_output.get("multi_condition_assessment") if isinstance(llm_output, dict) else None,
        "criteria_results": criteria_results,
    }

    return output_payload


def _build_input_sources(
    dataset_dir: Path,
    pattern: str,
    input_mode: str,
    json_pattern: str,
    criteria_for_dataset_json: list[dict[str, str]] | None,
    max_files: int | None,
    normalized_dataset_json_dir: Path | None,
) -> list[InputSourceRequests]:
    sources: list[InputSourceRequests] = []

    if input_mode == "dataset_json":
        if normalized_dataset_json_dir is None:
            raise ValueError("normalized dataset json directory is required in dataset_json mode")

        normalized_dataset_json_dir.mkdir(parents=True, exist_ok=True)
        json_files = sorted(path for path in dataset_dir.glob(json_pattern) if path.is_file())
        if max_files and max_files > 0:
            json_files = json_files[:max_files]

        for json_file in json_files:
            source_json_data_raw = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(source_json_data_raw, dict):
                raise ValueError(f"dataset json must be an object: {json_file}")

            source_json_data = copy.deepcopy(source_json_data_raw)
            criteria: list[dict[str, str]]
            source_criteria_mapping: list[dict[str, str]]
            criteria_warnings: list[str] = []

            if criteria_for_dataset_json is not None:
                criteria = copy.deepcopy(criteria_for_dataset_json)
                source_criteria_mapping = [
                    {
                        "source_key": f"criteria{idx}",
                        "title": criterion["title"],
                        "assertion": criterion["assertion"],
                    }
                    for idx, criterion in enumerate(criteria, start=1)
                ]
            else:
                criteria, source_criteria_mapping, criteria_warnings = _extract_criteria_from_dataset_json(source_json_data)

            normalized_json_path = normalized_dataset_json_dir / f"{json_file.stem}__normalized.json"
            warnings = _normalize_dataset_json_run_file(
                source_json_path=json_file,
                source_json_data=source_json_data,
                normalized_json_path=normalized_json_path,
            )
            warnings.extend(criteria_warnings)
            payload = {
                "conditions": [{"conditionID": str(normalized_json_path.resolve())}],
                "criteria": copy.deepcopy(criteria),
            }
            sources.append(
                InputSourceRequests(
                    source_name=json_file.name,
                    payloads=[payload],
                    warnings=warnings,
                    source_path=json_file,
                    source_json_data=source_json_data,
                    source_criteria_mapping=source_criteria_mapping,
                )
            )
        return sources

    txt_files = sorted(path for path in dataset_dir.glob(pattern) if path.is_file())
    if max_files and max_files > 0:
        txt_files = txt_files[:max_files]

    for txt_file in txt_files:
        parse_result = parse_requests_from_txt(txt_file)
        sources.append(
            InputSourceRequests(
                source_name=txt_file.name,
                payloads=parse_result.payloads,
                warnings=parse_result.warnings,
                source_path=txt_file,
            )
        )
    return sources


async def run_single_request(payload: dict[str, Any]) -> dict[str, Any]:
    request = ExperimentEvaluationRequest.model_validate(payload)
    services = get_judge_services()
    response = await evaluate_experiment(request, services)
    return response.model_dump(mode="json")


def _normalize_condition_lookup_ids(raw_condition_id: str) -> list[str]:
    normalized_candidates: list[str] = []

    def _append(candidate: str) -> None:
        if candidate and candidate not in normalized_candidates:
            normalized_candidates.append(candidate)

    base_name = str(raw_condition_id or "").replace("\\", "/").split("/")[-1].strip()
    stripped_raw = str(raw_condition_id or "").strip()

    while base_name.lower().endswith(".json"):
        base_name = base_name[:-5].strip()
    while stripped_raw.lower().endswith(".json"):
        stripped_raw = stripped_raw[:-5].strip()

    _append(base_name)
    _append(stripped_raw)
    return normalized_candidates


def _find_condition_json_path(condition_id: str, lookup_dirs: list[Path]) -> Path | None:
    lookup_ids = _normalize_condition_lookup_ids(condition_id)
    if not lookup_ids:
        return None

    for lookup_dir in lookup_dirs:
        for lookup_id in lookup_ids:
            candidate = lookup_dir / f"{lookup_id}.json"
            if candidate.exists() and candidate.is_file():
                return candidate

    return None


def _load_condition_run_payload(condition_id: str, lookup_dirs: list[Path]) -> dict[str, Any] | None:
    json_path = _find_condition_json_path(condition_id, lookup_dirs)
    if json_path is None:
        return None

    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_human_review_template(condition_output: dict[str, Any]) -> dict[str, Any]:
    criteria_reviews: list[dict[str, Any]] = []
    criteria_list = condition_output.get("criteria") if isinstance(condition_output, dict) else []
    if not isinstance(criteria_list, list):
        criteria_list = []

    for criterion_index, criterion in enumerate(criteria_list, start=1):
        if not isinstance(criterion, dict):
            continue

        criterion_title = str(
            criterion.get("title")
            or criterion.get("name")
            or f"criterion_{criterion_index}"
        )

        step_reviews: list[dict[str, Any]] = []
        involved_steps = criterion.get("involved_steps")
        if not isinstance(involved_steps, list):
            involved_steps = []

        for step_group_index, step_group in enumerate(involved_steps, start=1):
            if not isinstance(step_group, dict):
                continue

            step_indices = step_group.get("steps")
            if not isinstance(step_indices, list):
                step_indices = []

            normalized_step_indices = [
                int(step_index)
                for step_index in step_indices
                if isinstance(step_index, int)
            ]

            evidence_reviews: list[dict[str, Any]] = []
            highlighted_evidence = step_group.get("highlighted_evidence")
            if isinstance(highlighted_evidence, list):
                for evidence_index, evidence in enumerate(highlighted_evidence, start=1):
                    if not isinstance(evidence, dict):
                        continue

                    evidence_reviews.append(
                        {
                            "evidence_id": f"c{criterion_index:02d}_s{step_group_index:02d}_e{evidence_index:02d}",
                            "step_index": evidence.get("step_index"),
                            "source_field": evidence.get("source_field"),
                            "highlighted_text": evidence.get("highlighted_text"),
                            "llm_verdict": evidence.get("verdict"),
                            "human_verdict": None,
                            "relevance_score": None,
                            "grounding_score": None,
                            "clarity_score": None,
                            "comment": "",
                        }
                    )

            step_reviews.append(
                {
                    "step_group_id": f"c{criterion_index:02d}_s{step_group_index:02d}",
                    "step_indices": normalized_step_indices,
                    "llm_step_verdict": step_group.get("evaluateStatus"),
                    "llm_reasoning": step_group.get("reasoning"),
                    "human_step_verdict": None,
                    "human_step_score": None,
                    "comment": "",
                    "evidence_reviews": evidence_reviews,
                }
            )

        criteria_reviews.append(
            {
                "criterion_title": criterion_title,
                "criterion_assertion": criterion.get("assertion"),
                "llm_overall_assessment": criterion.get("overall_assessment"),
                "llm_overall_reasoning": criterion.get("overall_reasoning"),
                "human_overall_assessment": None,
                "human_overall_score": None,
                "comment": "",
                "step_reviews": step_reviews,
            }
        )

    return {
        "review_status": "pending",
        "reviewed_by": None,
        "reviewed_at": None,
        "scoring_scale": {
            "score_min": 1,
            "score_max": 5,
            "description": "1=very poor, 5=very good",
        },
        "criteria_reviews": criteria_reviews,
    }


def _build_annotatable_request_package(
    source_file: str,
    request_index: int,
    request_payload: dict[str, Any],
    llm_output: dict[str, Any],
    condition_lookup_dirs: list[Path],
    condition_payload_cache: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    merged_conditions: list[dict[str, Any]] = []
    warnings: list[str] = []

    conditions_output = llm_output.get("conditions")
    if not isinstance(conditions_output, list):
        conditions_output = []

    for condition_output in conditions_output:
        if not isinstance(condition_output, dict):
            continue

        condition_id = str(condition_output.get("conditionID") or "").strip()
        run_payload = condition_payload_cache.get(condition_id)
        if condition_id and condition_id not in condition_payload_cache:
            run_payload = _load_condition_run_payload(condition_id, condition_lookup_dirs)
            condition_payload_cache[condition_id] = run_payload

        if condition_id and run_payload is None:
            warnings.append(f"Condition source data not found for conditionID='{condition_id}'")

        source_data = None
        if isinstance(run_payload, dict):
            source_data = {
                "metadata": run_payload.get("metadata", {}),
                "summary": run_payload.get("summary", {}),
                "details": run_payload.get("details", {}),
            }

        merged_condition = {
            **condition_output,
            "data": source_data,
            "human_review": _build_human_review_template(condition_output),
        }
        merged_conditions.append(merged_condition)

    return {
        "source_file": source_file,
        "request_index": request_index,
        "request": request_payload,
        "llm_output": llm_output,
        "conditions": merged_conditions,
        "multi_condition_assessment": llm_output.get("multi_condition_assessment"),
        "warnings": warnings,
    }


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


async def run_batch(
    dataset_dir: Path,
    results_dir: Path,
    pattern: str,
    fail_fast: bool,
    forced_granularity: str | None,
    run_tag: str | None,
    emit_annotatable_output: bool,
    max_files: int | None,
    max_conditions_per_request: int | None,
    judge_models: list[str] | None,
    input_mode: str,
    json_pattern: str,
    criteria_for_dataset_json: list[dict[str, str]] | None,
    fixed_batch_id: str | None,
) -> int:
    results_dir.mkdir(parents=True, exist_ok=True)

    batch_id = (fixed_batch_id or "").strip() or _timestamp()
    normalized_dataset_json_dir: Path | None = None
    if input_mode == "dataset_json":
        normalized_dataset_json_dir = results_dir / f"_normalized_dataset_json_{batch_id}"
        if normalized_dataset_json_dir.exists() and normalized_dataset_json_dir.is_dir():
            # Avoid stale normalized files when reusing a fixed batch id.
            shutil.rmtree(normalized_dataset_json_dir)

    input_sources = _build_input_sources(
        dataset_dir=dataset_dir,
        pattern=pattern,
        input_mode=input_mode,
        json_pattern=json_pattern,
        criteria_for_dataset_json=criteria_for_dataset_json,
        max_files=max_files,
        normalized_dataset_json_dir=normalized_dataset_json_dir,
    )

    if not input_sources:
        if input_mode == "dataset_json":
            print(f"[WARN] No matching top-level json files in dataset directory: {dataset_dir} / {json_pattern}")
        else:
            print(f"[WARN] No matching files in dataset directory: {dataset_dir} / {pattern}")
        return 1

    summary: dict[str, Any] = {
        "batch_id": batch_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_dir": str(dataset_dir),
        "results_dir": str(results_dir),
        "forced_granularity": forced_granularity,
        "run_tag": run_tag,
        "input_mode": input_mode,
        "json_pattern": json_pattern,
        "max_files": max_files,
        "max_conditions_per_request": max_conditions_per_request,
        "judge_models": judge_models or [],
        "files": [],
    }
    if normalized_dataset_json_dir is not None:
        summary["normalized_dataset_json_dir"] = str(normalized_dataset_json_dir)

    total_requests = 0
    success_requests = 0

    condition_lookup_dirs: list[Path] = []
    condition_payload_cache: dict[str, dict[str, Any] | None] = {}
    if emit_annotatable_output and input_mode != "dataset_json":
        condition_lookup_dirs = get_condition_lookup_dirs(settings)
        summary["condition_lookup_dirs"] = [str(path) for path in condition_lookup_dirs]

    for source in input_sources:
        file_result: dict[str, Any] = {
            "file": source.source_name,
            "status": "ok",
            "warnings": [],
            "requests": [],
        }

        try:
            file_result["warnings"].extend(source.warnings)

            if not source.payloads:
                raise ValueError("No executable evaluation request recognized in txt (must contain conditions + criteria)")

            for idx, payload in enumerate(source.payloads, start=1):
                base_payload = copy.deepcopy(payload)

                if forced_granularity:
                    base_payload["forced_granularity"] = forced_granularity

                original_conditions = base_payload.get("conditions")
                if (
                    isinstance(original_conditions, list)
                    and max_conditions_per_request
                    and max_conditions_per_request > 0
                    and len(original_conditions) > max_conditions_per_request
                ):
                    base_payload["conditions"] = original_conditions[:max_conditions_per_request]
                    file_result["warnings"].append(
                        f"Request {idx}: conditions truncated from {len(original_conditions)} to {max_conditions_per_request}"
                    )

                model_candidates = judge_models or []
                if not model_candidates:
                    payload_model = base_payload.get("judge_model")
                    if isinstance(payload_model, str) and payload_model.strip():
                        model_candidates = [payload_model.strip()]
                if not model_candidates:
                    model_candidates = [""]

                for model_idx, model_name in enumerate(model_candidates, start=1):
                    total_requests += 1

                    payload_for_run = copy.deepcopy(base_payload)
                    if model_name:
                        payload_for_run["judge_model"] = model_name

                    suffix_parts = []
                    if run_tag:
                        suffix_parts.append(run_tag)
                    if forced_granularity:
                        suffix_parts.append(forced_granularity)
                    if model_name:
                        suffix_parts.append(f"judge-{_safe_filename_token(model_name)}")
                    if len(model_candidates) > 1:
                        suffix_parts.append(f"m{model_idx:02d}")
                    suffix = "__" + "__".join(suffix_parts) if suffix_parts else ""

                    if input_mode == "dataset_json":
                        output_name = f"{Path(source.source_name).stem}__req{idx:02d}{suffix}__evaluated.json"
                    else:
                        output_name = f"{Path(source.source_name).stem}__req{idx:02d}{suffix}__result.json"
                    output_path = results_dir / output_name

                    request_item = {
                        "request_index": idx,
                        "model_index": model_idx,
                        "judge_model": payload_for_run.get("judge_model"),
                        "condition_count": len(payload_for_run.get("conditions", [])) if isinstance(payload_for_run.get("conditions"), list) else None,
                        "output_file": output_name,
                        "status": "ok",
                    }

                    try:
                        result = await run_single_request(payload_for_run)

                        if input_mode == "dataset_json" and isinstance(source.source_json_data, dict):
                            output_payload = _build_dataset_json_appended_output(
                                source_json_data=source.source_json_data,
                                source_file=source.source_name,
                                request_payload=payload_for_run,
                                llm_output=result,
                                source_criteria_mapping=source.source_criteria_mapping,
                                output_file=output_name,
                            )
                            output_path.write_text(
                                json.dumps(output_payload, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                        else:
                            annotatable_output_name = output_name.replace("__result.json", "__annotatable.json")
                            annotatable_output_path = results_dir / annotatable_output_name

                            output_path.write_text(
                                json.dumps(
                                    {
                                        "source_file": source.source_name,
                                        "request_index": idx,
                                        "request": payload_for_run,
                                        "result": result,
                                    },
                                    indent=2,
                                    ensure_ascii=False,
                                ),
                                encoding="utf-8",
                            )

                            if emit_annotatable_output:
                                annotatable_package = _build_annotatable_request_package(
                                    source_file=source.source_name,
                                    request_index=idx,
                                    request_payload=payload_for_run,
                                    llm_output=result,
                                    condition_lookup_dirs=condition_lookup_dirs,
                                    condition_payload_cache=condition_payload_cache,
                                )
                                annotatable_output_path.write_text(
                                    json.dumps(annotatable_package, indent=2, ensure_ascii=False),
                                    encoding="utf-8",
                                )
                                request_item["annotatable_output_file"] = annotatable_output_name
                                if annotatable_package.get("warnings"):
                                    file_result["warnings"].extend(annotatable_package["warnings"])

                        success_requests += 1
                    except Exception as exc:
                        request_item["status"] = "error"
                        request_item["error"] = str(exc)
                        file_result["status"] = "partial_error"
                        if fail_fast:
                            file_result["requests"].append(request_item)
                            raise

                    file_result["requests"].append(request_item)

        except Exception as exc:
            file_result["status"] = "error"
            file_result["error"] = str(exc)
            if fail_fast:
                summary["files"].append(file_result)
                break

        summary["files"].append(file_result)

    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    summary["total_files"] = len(summary["files"])
    summary["total_requests"] = total_requests
    summary["success_requests"] = success_requests
    summary["failed_requests"] = total_requests - success_requests

    summary_path = results_dir / f"batch_summary_{batch_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[DONE] Batch: {batch_id}")
    print(f"[DONE] Summary: {summary_path}")
    print(f"[DONE] Requests: success={success_requests}, failed={total_requests - success_requests}")

    return 0 if (total_requests > 0 and success_requests == total_requests) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch run Agentic Judge technical evaluation")
    parser.add_argument(
        "--dataset-dir",
        default=str(Path(__file__).resolve().parent / "dataset"),
        help="Input txt data directory",
    )
    parser.add_argument(
        "--results-dir",
        default=str(Path(__file__).resolve().parent / "results"),
        help="Evaluation results output directory",
    )
    parser.add_argument(
        "--pattern",
        default="*.txt",
        help="Glob pattern for matching data files, default *.txt",
    )
    parser.add_argument(
        "--input-mode",
        choices=["txt_requests", "dataset_json"],
        default="txt_requests",
        help="txt_requests: parse requests from txt files; dataset_json: evaluate each top-level dataset json file directly",
    )
    parser.add_argument(
        "--json-pattern",
        default="*.json",
        help="Top-level glob used when --input-mode=dataset_json (subfolders are ignored)",
    )
    parser.add_argument(
        "--criteria-file",
        default=None,
        help="Optional criteria JSON file used with --input-mode=dataset_json",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately on first error",
    )
    parser.add_argument(
        "--forced-granularity",
        choices=["step_level", "phase_level", "global_summary"],
        default=None,
        help="Force all criteria to a single granularity baseline",
    )
    parser.add_argument(
        "--run-tag",
        default=None,
        help="Optional tag appended to output file names for experiment tracking",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional limit on number of dataset files matched by --pattern / --json-pattern",
    )
    parser.add_argument(
        "--max-conditions-per-request",
        type=int,
        default=None,
        help="Optional limit on condition count per parsed request payload",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Optional single judge model override for all requests in this run",
    )
    parser.add_argument(
        "--judge-models",
        nargs="+",
        default=None,
        help="Optional list of judge models (space or comma separated) to run for each request",
    )
    parser.add_argument(
        "--skip-annotatable-output",
        action="store_true",
        help="Skip writing data+LLM output files used for manual verdict/evidence scoring",
    )
    parser.add_argument(
        "--fixed-batch-id",
        default=None,
        help="Optional fixed batch id to overwrite summary/merged outputs (e.g. latest)",
    )
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    results_dir = Path(args.results_dir).resolve()

    if not dataset_dir.exists() or not dataset_dir.is_dir():
        print(f"[ERROR] dataset directory does not exist: {dataset_dir}")
        return 1

    model_overrides = _normalize_model_overrides(args.judge_models)
    if args.judge_model:
        model_overrides = _normalize_model_overrides([args.judge_model])

    criteria_for_dataset_json: list[dict[str, str]] | None = None
    if args.criteria_file:
        criteria_for_dataset_json = _load_criteria_from_file(Path(args.criteria_file).resolve())
    elif args.input_mode == "dataset_json":
        print("[INFO] --criteria-file not provided; extracting criteria from each source dataset json (fallback: Task Completion)")

    fixed_batch_id: str | None = None
    if args.fixed_batch_id:
        candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", str(args.fixed_batch_id).strip()).strip("-._")
        fixed_batch_id = candidate or None

    return asyncio.run(
        run_batch(
            dataset_dir=dataset_dir,
            results_dir=results_dir,
            pattern=args.pattern,
            fail_fast=args.fail_fast,
            forced_granularity=args.forced_granularity,
            run_tag=args.run_tag,
            emit_annotatable_output=not args.skip_annotatable_output,
            max_files=args.max_files,
            max_conditions_per_request=args.max_conditions_per_request,
            judge_models=model_overrides,
            input_mode=args.input_mode,
            json_pattern=args.json_pattern,
            criteria_for_dataset_json=criteria_for_dataset_json,
            fixed_batch_id=fixed_batch_id,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
