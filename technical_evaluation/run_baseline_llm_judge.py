from __future__ import annotations

# pyright: reportMissingImports=false

import argparse
import asyncio
import copy
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


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


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s - %(message)s",
        force=True,
    )


_bootstrap_env()
_configure_logging()

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.services.llm_factory import ChatLLMFactory


DEFAULT_DATASET_JSON_CRITERIA: list[dict[str, str]] = [
    {
        "title": "Task Completion",
        "assertion": "The agent completes the assigned user task successfully and reaches the intended end state.",
        "description": "Judge completion quality using execution trace, final result, and consistency of actions.",
    }
]


ALLOWED_SOURCE_FIELDS = {
    "evaluation": "Evaluation",
    "memory": "Memory",
    "thinking process": "Thinking Process",
    "thinking_process": "Thinking Process",
    "thinking": "Thinking Process",
    "next goal": "Next Goal",
    "next_goal": "Next Goal",
    "action": "Action",
}


@dataclass
class InputSource:
    source_name: str
    source_path: Path
    source_json_data: dict[str, Any]
    criteria: list[dict[str, str]]
    source_criteria_mapping: list[dict[str, str]]
    warnings: list[str]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


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


def _criterion_sort_key(raw_key: str) -> tuple[int, str]:
    match = re.fullmatch(r"criteria(\d+)", str(raw_key).strip(), re.IGNORECASE)
    if match:
        return (int(match.group(1)), str(raw_key))
    return (10_000, str(raw_key))


def _extract_criteria_from_dataset_json(
    source_json: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
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
    return copy.deepcopy(DEFAULT_DATASET_JSON_CRITERIA), [
        {
            "source_key": "criteria1",
            "title": DEFAULT_DATASET_JSON_CRITERIA[0]["title"],
            "assertion": DEFAULT_DATASET_JSON_CRITERIA[0]["assertion"],
        }
    ], warnings


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


def _normalize_source_field(raw_field: Any) -> str:
    text = str(raw_field or "").strip().lower().replace("-", " ")
    text = " ".join(text.split())
    return ALLOWED_SOURCE_FIELDS.get(text, "Evaluation")


def _normalize_step_verdict(raw: Any) -> str:
    lowered = str(raw or "").strip().lower()
    if lowered in {"pass", "fail", "partial", "unknown"}:
        return lowered
    if lowered in {"unable_to_evaluate", "n/a", "none", ""}:
        return "unknown"
    return "unknown"


def _normalize_final_verdict(raw: Any) -> str:
    """Final verdicts must not contain `partial`."""
    lowered = _normalize_step_verdict(raw)
    if lowered == "partial":
        return "fail"
    return lowered


def _clip_confidence(raw: Any, default: float = 0.0) -> float:
    try:
        value = float(raw)
    except Exception:
        value = default
    return max(0.0, min(1.0, value))


def _response_to_text(response_obj: Any) -> str:
    if response_obj is None:
        return ""

    content = getattr(response_obj, "content", None)
    if isinstance(content, str):
        return content
    if content is not None:
        try:
            return json.dumps(content, ensure_ascii=False, indent=2)
        except Exception:
            return str(content)

    text = getattr(response_obj, "text", None)
    if isinstance(text, str):
        return text

    return str(response_obj)


def _extract_json_object(response_text: str) -> dict[str, Any] | None:
    if not response_text:
        return None

    stripped = response_text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        candidate = fenced_match.group(1).strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    start = stripped.find("{")
    end = stripped.rfind("}") + 1
    if start == -1 or end <= start:
        return None

    try:
        parsed = json.loads(stripped[start:end])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _build_input_sources(
    dataset_dir: Path,
    json_pattern: str,
    max_files: int | None,
    criteria_for_dataset_json: list[dict[str, str]] | None,
) -> list[InputSource]:
    json_files = sorted(path for path in dataset_dir.glob(json_pattern) if path.is_file())
    if max_files and max_files > 0:
        json_files = json_files[:max_files]

    sources: list[InputSource] = []
    for json_file in json_files:
        source_json_data_raw = json.loads(json_file.read_text(encoding="utf-8"))
        if not isinstance(source_json_data_raw, dict):
            raise ValueError(f"dataset json must be an object: {json_file}")

        source_json_data = copy.deepcopy(source_json_data_raw)

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
            criteria_warnings: list[str] = []
        else:
            criteria, source_criteria_mapping, criteria_warnings = _extract_criteria_from_dataset_json(source_json_data)

        sources.append(
            InputSource(
                source_name=json_file.name,
                source_path=json_file,
                source_json_data=source_json_data,
                criteria=criteria,
                source_criteria_mapping=source_criteria_mapping,
                warnings=criteria_warnings,
            )
        )

    return sources


def _normalize_step_records(
    source_json_data: dict[str, Any],
    max_steps: int | None,
    max_chars_per_field: int | None,
) -> list[dict[str, Any]]:
    raw_steps = source_json_data.get("steps")
    if not isinstance(raw_steps, list):
        return []

    clipped_steps = raw_steps
    if max_steps and max_steps > 0:
        clipped_steps = raw_steps[:max_steps]

    char_limit = max_chars_per_field if isinstance(max_chars_per_field, int) and max_chars_per_field > 0 else None

    def _clip(value: Any) -> str:
        text = str(value or "")
        if char_limit is None:
            return text
        return text[:char_limit]

    steps_for_prompt: list[dict[str, Any]] = []
    for idx, step in enumerate(clipped_steps):
        if not isinstance(step, dict):
            continue

        step_id_raw = step.get("step_id")
        if isinstance(step_id_raw, int):
            step_id = step_id_raw
        elif isinstance(step_id_raw, str) and step_id_raw.isdigit():
            step_id = int(step_id_raw)
        else:
            step_id = idx + 1

        steps_for_prompt.append(
            {
                "step_index": idx,
                "step_id": step_id,
                "evaluation": _clip(step.get("EVALUATION") or step.get("evaluation_previous_goal")),
                "memory": _clip(step.get("MEMORY") or step.get("memory")),
                "thinking_process": _clip(step.get("AI REASONING") or step.get("thinking") or step.get("thinking_process")),
                "next_goal": _clip(step.get("TARGET OBJECTIVE") or step.get("next_goal")),
                "action": _clip(step.get("ACTION") or step.get("action")),
            }
        )

    return steps_for_prompt


def _build_baseline_prompt(
    source_name: str,
    source_json_data: dict[str, Any],
    request_payload: dict[str, Any],
    max_steps: int | None,
    max_chars_per_field: int | None,
) -> str:
    fallback_task_name = Path(source_name).stem
    task_name, task_url = _extract_task_name_and_url(str(source_json_data.get("task") or ""), fallback_task_name)
    source_model = str(source_json_data.get("model") or "").strip()
    final_result = str(source_json_data.get("final_result") or "").strip()
    criteria = request_payload.get("criteria") if isinstance(request_payload.get("criteria"), list) else []

    steps_for_prompt = _normalize_step_records(
        source_json_data=source_json_data,
        max_steps=max_steps,
        max_chars_per_field=max_chars_per_field,
    )

    return (
        "You are an expert evaluator for LLM-as-a-judge baseline.\n"
        "You must evaluate ALL criteria in one single pass from raw trace data.\n"
        "Do not use multi-stage agentic reasoning.\n"
        "\n"
        "Return ONLY a single valid JSON object (no markdown, no prose) with this exact top-level shape:\n"
        "{\n"
        "  \"criteria\": [\n"
        "    {\n"
        "      \"title\": \"string, exactly match input criterion title\",\n"
        "      \"overall_assessment\": \"pass|fail|unknown\",\n"
        "      \"overall_reasoning\": \"string\",\n"
        "      \"confidence\": 0.0,\n"
        "      \"involved_steps\": [\n"
        "        {\n"
        "          \"evaluateStatus\": \"pass|fail|partial|unknown\",\n"
        "          \"reasoning\": \"string\",\n"
        "          \"confidenceScore\": 0.0,\n"
        "          \"steps\": [0],\n"
        "          \"highlighted_evidence\": [\n"
        "            {\n"
        "              \"step_index\": 0,\n"
        "              \"source_field\": \"Evaluation|Memory|Thinking Process|Next Goal|Action\",\n"
        "              \"highlighted_text\": \"string\",\n"
        "              \"reasoning\": \"string\",\n"
        "              \"verdict\": \"pass|fail|partial|unknown\"\n"
        "            }\n"
        "          ]\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "\n"
        "Rules:\n"
        "- Every input criterion must appear exactly once in output criteria list.\n"
        "- Final criterion `overall_assessment` must be one of: pass, fail, unknown (do not output partial).\n"
        "- `steps` and `step_index` use 0-based indexing aligned to provided step_index.\n"
        "- Keep confidence/confidenceScore in [0, 1].\n"
        "- Use short evidence snippets grounded in the given step fields.\n"
        "\n"
        f"Source file: {source_name}\n"
        f"Task name: {task_name}\n"
        f"Task url: {task_url}\n"
        f"Source model: {source_model}\n"
        f"Final result: {final_result}\n"
        "\n"
        "Criteria JSON:\n"
        f"{json.dumps(criteria, ensure_ascii=False, indent=2)}\n"
        "\n"
        "Raw steps JSON:\n"
        f"{json.dumps(steps_for_prompt, ensure_ascii=False, indent=2)}\n"
    )


def _normalize_evidence_item(
    raw_item: Any,
    fallback_step_indices: list[int],
) -> dict[str, Any] | None:
    if not isinstance(raw_item, dict):
        return None

    step_index_raw = raw_item.get("step_index")
    if isinstance(step_index_raw, int):
        step_index = step_index_raw
    elif isinstance(step_index_raw, str) and step_index_raw.strip().isdigit():
        step_index = int(step_index_raw.strip())
    elif fallback_step_indices:
        step_index = int(fallback_step_indices[0])
    else:
        step_index = 0

    highlighted_text = str(raw_item.get("highlighted_text") or "").strip()
    if not highlighted_text:
        return None

    return {
        "step_index": step_index,
        "source_field": _normalize_source_field(raw_item.get("source_field")),
        "highlighted_text": highlighted_text,
        "reasoning": str(raw_item.get("reasoning") or "").strip(),
        "verdict": _normalize_step_verdict(raw_item.get("verdict")),
    }


def _normalize_involved_step_group(raw_group: Any) -> dict[str, Any] | None:
    if not isinstance(raw_group, dict):
        return None

    steps_raw = raw_group.get("steps")
    step_indices: list[int] = []
    if isinstance(steps_raw, list):
        for item in steps_raw:
            if isinstance(item, int):
                step_indices.append(item)
            elif isinstance(item, str) and item.strip().isdigit():
                step_indices.append(int(item.strip()))

    highlighted_raw = raw_group.get("highlighted_evidence")
    highlighted_evidence: list[dict[str, Any]] = []
    if isinstance(highlighted_raw, list):
        for item in highlighted_raw:
            normalized_item = _normalize_evidence_item(item, step_indices)
            if normalized_item is not None:
                highlighted_evidence.append(normalized_item)

    if not step_indices and highlighted_evidence:
        step_indices = [int(item["step_index"]) for item in highlighted_evidence if isinstance(item.get("step_index"), int)]

    step_indices = sorted({int(idx) for idx in step_indices if isinstance(idx, int)})

    return {
        "evaluateStatus": _normalize_step_verdict(raw_group.get("evaluateStatus") or raw_group.get("verdict")),
        "reasoning": str(raw_group.get("reasoning") or "").strip(),
        "highlighted_evidence": highlighted_evidence,
        "confidenceScore": _clip_confidence(raw_group.get("confidenceScore"), default=0.0),
        "steps": step_indices,
    }


def _criteria_candidates_from_response(response_payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_keys = ["criteria", "criteria_results", "results"]
    for key in candidate_keys:
        value = response_payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    # Fallback: collect dict values that look like criterion results.
    inferred: list[dict[str, Any]] = []
    for key, value in response_payload.items():
        if not isinstance(value, dict):
            continue
        if any(field in value for field in ["overall_assessment", "involved_steps", "overall_reasoning"]):
            item = dict(value)
            if not item.get("title"):
                item["title"] = str(key)
            inferred.append(item)
    return inferred


def _build_baseline_response_shape(
    source_name: str,
    source_json_data: dict[str, Any],
    request_payload: dict[str, Any],
    llm_parsed_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    request_criteria = request_payload.get("criteria") if isinstance(request_payload.get("criteria"), list) else []
    conditions = request_payload.get("conditions") if isinstance(request_payload.get("conditions"), list) else []
    condition_id = ""
    if conditions and isinstance(conditions[0], dict):
        condition_id = str(conditions[0].get("conditionID") or "").strip()
    if not condition_id:
        condition_id = Path(source_name).stem

    persona = str(source_json_data.get("persona") or "")
    value = _infer_value_from_persona(persona)
    source_model = str(source_json_data.get("model") or "")

    parsed_criteria_list = _criteria_candidates_from_response(llm_parsed_payload or {})
    parsed_by_title: dict[str, dict[str, Any]] = {}
    for item in parsed_criteria_list:
        title = str(item.get("title") or "").strip()
        if title and title not in parsed_by_title:
            parsed_by_title[title] = item

    criteria_results: list[dict[str, Any]] = []
    for criterion in request_criteria:
        if not isinstance(criterion, dict):
            continue

        title = str(criterion.get("title") or "").strip()
        parsed_item = parsed_by_title.get(title, {})

        involved_steps_raw = parsed_item.get("involved_steps")
        normalized_involved_steps: list[dict[str, Any]] = []
        if isinstance(involved_steps_raw, list):
            for group in involved_steps_raw:
                normalized_group = _normalize_involved_step_group(group)
                if normalized_group is not None:
                    normalized_involved_steps.append(normalized_group)

        if not normalized_involved_steps:
            normalized_involved_steps = [
                {
                    "evaluateStatus": "unknown",
                    "reasoning": "No step-level evidence generated by baseline response.",
                    "highlighted_evidence": [],
                    "confidenceScore": 0.0,
                    "steps": [],
                }
            ]

        criteria_results.append(
            {
                "title": title,
                "assertion": str(criterion.get("assertion") or "").strip(),
                "description": str(criterion.get("description") or "").strip() or None,
                "involved_steps": normalized_involved_steps,
                "overall_assessment": _normalize_final_verdict(parsed_item.get("overall_assessment") or parsed_item.get("verdict")),
                "overall_reasoning": str(parsed_item.get("overall_reasoning") or parsed_item.get("reasoning") or "").strip(),
                "confidence": _clip_confidence(parsed_item.get("confidence"), default=0.0),
            }
        )

    return {
        "conditions": [
            {
                "conditionID": condition_id,
                "persona": persona,
                "value": value,
                "model": source_model,
                "run_index": 1,
                "criteria": criteria_results,
            }
        ],
        "multi_condition_assessment": None,
    }


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


def _get_model_results_folder_name(model_name: str) -> str:
    normalized = str(model_name or "")
    if not normalized.strip():
        return "Model"

    lower = normalized.strip().lower()
    if re.search(r"deepseek", lower):
        return "Deepseek"
    if re.search(r"(^|[^a-z])gpt([^a-z]|$)", lower) or re.search(r"openai", lower):
        return "GPT"

    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("-._")
    return sanitized or "Model"


async def _run_single_baseline_request(
    llm_factory: ChatLLMFactory,
    source: InputSource,
    payload_for_run: dict[str, Any],
    judge_model: str,
    show_llm_io: bool,
    max_steps: int | None,
    max_chars_per_field: int | None,
) -> dict[str, Any]:
    prompt = _build_baseline_prompt(
        source_name=source.source_name,
        source_json_data=source.source_json_data,
        request_payload=payload_for_run,
        max_steps=max_steps,
        max_chars_per_field=max_chars_per_field,
    )

    llm = llm_factory.get_langchain_llm(model=judge_model)
    response = await asyncio.to_thread(llm.invoke, prompt)
    response_text = _response_to_text(response)

    if show_llm_io:
        print("[BASELINE][PROMPT] ===== START =====")
        print(prompt)
        print("[BASELINE][PROMPT] ===== END =====")
        print("[BASELINE][RESPONSE] ===== START =====")
        print(response_text)
        print("[BASELINE][RESPONSE] ===== END =====")

    parsed = _extract_json_object(response_text)
    if parsed is None:
        parsed = {}

    return _build_baseline_response_shape(
        source_name=source.source_name,
        source_json_data=source.source_json_data,
        request_payload=payload_for_run,
        llm_parsed_payload=parsed,
    )


async def _run_batch_for_model(
    dataset_dir: Path,
    results_dir: Path,
    json_pattern: str,
    fail_fast: bool,
    run_tag: str | None,
    max_files: int | None,
    judge_model: str,
    criteria_for_dataset_json: list[dict[str, str]] | None,
    fixed_batch_id: str | None,
    request_max_concurrency: int,
    skip_existing: bool,
    show_llm_io: bool,
    max_steps: int | None,
    max_chars_per_field: int | None,
) -> int:
    batch_started_at = time.perf_counter()
    results_dir.mkdir(parents=True, exist_ok=True)

    batch_id = (fixed_batch_id or "").strip() or _timestamp()
    input_sources = _build_input_sources(
        dataset_dir=dataset_dir,
        json_pattern=json_pattern,
        max_files=max_files,
        criteria_for_dataset_json=criteria_for_dataset_json,
    )

    if not input_sources:
        print(f"[WARN] No matching top-level json files in dataset directory: {dataset_dir} / {json_pattern}")
        return 1

    summary: dict[str, Any] = {
        "batch_id": batch_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_dir": str(dataset_dir),
        "results_dir": str(results_dir),
        "run_tag": run_tag,
        "input_mode": "dataset_json",
        "json_pattern": json_pattern,
        "max_files": max_files,
        "judge_model": judge_model,
        "request_max_concurrency": max(1, int(request_max_concurrency or 1)),
        "skip_existing": bool(skip_existing),
        "baseline_mode": "one_shot_prompt",
        "files": [],
    }

    total_requests = 0
    success_requests = 0
    failed_requests = 0
    skipped_requests = 0

    llm_factory = ChatLLMFactory()
    request_jobs: list[dict[str, Any]] = []
    stop_after_build = False

    for source in input_sources:
        file_result: dict[str, Any] = {
            "file": source.source_name,
            "status": "ok",
            "warnings": list(source.warnings),
            "requests": [],
        }
        summary["files"].append(file_result)
        file_result_index = len(summary["files"]) - 1

        try:
            payload_for_run: dict[str, Any] = {
                "conditions": [{"conditionID": source.source_path.stem}],
                "criteria": copy.deepcopy(source.criteria),
                "judge_model": judge_model,
            }

            total_requests += 1
            suffix_parts = []
            if run_tag:
                suffix_parts.append(run_tag)
            if judge_model:
                suffix_parts.append(f"judge-{_safe_filename_token(judge_model)}")
            suffix = "__" + "__".join(suffix_parts) if suffix_parts else ""
            output_name = f"{Path(source.source_name).stem}__req01{suffix}__evaluated.json"
            output_path = results_dir / output_name

            request_item = {
                "request_index": 1,
                "model_index": 1,
                "judge_model": judge_model,
                "condition_count": 1,
                "output_file": output_name,
                "status": "pending",
            }
            file_result["requests"].append(request_item)
            request_jobs.append(
                {
                    "source": source,
                    "file_result_index": file_result_index,
                    "request_result_index": 0,
                    "payload_for_run": payload_for_run,
                    "output_name": output_name,
                    "output_path": output_path,
                }
            )
        except Exception as exc:
            file_result["status"] = "error"
            file_result["error"] = str(exc)
            if fail_fast:
                stop_after_build = True
                break

    async def _run_request_job(job: dict[str, Any]) -> dict[str, Any]:
        source: InputSource = job["source"]
        payload_for_run: dict[str, Any] = job["payload_for_run"]
        output_path: Path = job["output_path"]
        output_name: str = job["output_name"]

        started_at = time.perf_counter()
        request_update: dict[str, Any] = {"status": "ok"}

        if skip_existing and output_path.exists():
            request_update["status"] = "skipped"
            request_update["skip_reason"] = "output_exists"
            request_update["duration_seconds"] = round(time.perf_counter() - started_at, 3)
            return {
                "file_result_index": job["file_result_index"],
                "request_result_index": job["request_result_index"],
                "request_update": request_update,
                "file_warnings": [],
            }

        try:
            llm_output = await _run_single_baseline_request(
                llm_factory=llm_factory,
                source=source,
                payload_for_run=payload_for_run,
                judge_model=judge_model,
                show_llm_io=show_llm_io,
                max_steps=max_steps,
                max_chars_per_field=max_chars_per_field,
            )
            output_payload = _build_dataset_json_appended_output(
                source_json_data=source.source_json_data,
                source_file=source.source_name,
                request_payload=payload_for_run,
                llm_output=llm_output,
                source_criteria_mapping=source.source_criteria_mapping,
                output_file=output_name,
            )
            output_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            request_update["status"] = "error"
            request_update["error"] = str(exc)

        request_update["duration_seconds"] = round(time.perf_counter() - started_at, 3)
        return {
            "file_result_index": job["file_result_index"],
            "request_result_index": job["request_result_index"],
            "request_update": request_update,
            "file_warnings": [],
        }

    def _apply_job_result(job_result: dict[str, Any]) -> None:
        nonlocal success_requests, failed_requests, skipped_requests

        file_result_index = int(job_result["file_result_index"])
        request_result_index = int(job_result["request_result_index"])
        file_result = summary["files"][file_result_index]
        request_item = file_result["requests"][request_result_index]
        request_update = job_result.get("request_update") or {}

        request_item.update(request_update)

        status = str(request_item.get("status") or "")
        if status == "ok":
            success_requests += 1
        elif status == "skipped":
            skipped_requests += 1
        elif status == "error":
            failed_requests += 1
            if file_result.get("status") == "ok":
                file_result["status"] = "partial_error"

    if not stop_after_build:
        effective_request_concurrency = max(1, int(request_max_concurrency or 1))
        if fail_fast and effective_request_concurrency > 1:
            print("[INFO] --fail-fast enabled; forcing request concurrency to 1")
            effective_request_concurrency = 1

        if effective_request_concurrency > 1:
            semaphore = asyncio.Semaphore(effective_request_concurrency)

            async def _guarded_run(job: dict[str, Any]) -> dict[str, Any]:
                async with semaphore:
                    return await _run_request_job(job)

            job_results = await asyncio.gather(*[_guarded_run(job) for job in request_jobs])
            for job_result in job_results:
                _apply_job_result(job_result)
        else:
            for job in request_jobs:
                job_result = await _run_request_job(job)
                _apply_job_result(job_result)

                request_update = job_result.get("request_update") or {}
                if fail_fast and request_update.get("status") == "error":
                    break

    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    summary["duration_seconds"] = round(time.perf_counter() - batch_started_at, 3)
    summary["total_files"] = len(summary["files"])
    summary["total_requests"] = total_requests
    summary["executed_requests"] = success_requests + failed_requests
    summary["skipped_requests"] = skipped_requests
    summary["success_requests"] = success_requests
    summary["failed_requests"] = failed_requests

    summary_path = results_dir / f"batch_summary_{batch_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[DONE] Baseline batch: {batch_id}")
    print(f"[DONE] Summary: {summary_path}")
    print(
        f"[DONE] Requests: success={success_requests}, skipped={skipped_requests}, "
        f"failed={failed_requests}, total={total_requests}"
    )

    return 0 if (total_requests > 0 and failed_requests == 0 and (success_requests + skipped_requests) == total_requests) else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one-shot (non-agentic) LLM-as-a-judge baseline on raw dataset JSON files"
    )
    parser.add_argument(
        "--dataset-dir",
        default=str(Path(__file__).resolve().parent / "dataset"),
        help="Input dataset JSON directory",
    )
    parser.add_argument(
        "--results-dir",
        default=str(Path(__file__).resolve().parent / "results" / "baseline"),
        help="Baseline evaluation output directory",
    )
    parser.add_argument(
        "--json-pattern",
        default="*.json",
        help="Top-level glob for dataset JSON files (subfolders are ignored)",
    )
    parser.add_argument(
        "--criteria-file",
        default=None,
        help="Optional criteria JSON file; if omitted, criteria are extracted from each source JSON",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Optional single judge model override for this run",
    )
    parser.add_argument(
        "--judge-models",
        nargs="+",
        default=["deepseek-chat", "gpt-5"],
        help="Judge models to run (space or comma separated), default: deepseek-chat gpt-5",
    )
    parser.add_argument(
        "--run-tag",
        default="baseline_oneshot",
        help="Tag appended to output filenames",
    )
    parser.add_argument(
        "--fixed-batch-id",
        default="latest",
        help="Fixed batch id to allow deterministic overwrite (default: latest)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional limit on number of top-level json files",
    )
    parser.add_argument(
        "--request-max-concurrency",
        type=int,
        default=2,
        help="Max number of requests to evaluate concurrently (default: 2)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Optional maximum number of steps sent to one-shot baseline prompt",
    )
    parser.add_argument(
        "--max-chars-per-field",
        type=int,
        default=700,
        help="Max chars per step field in prompt payload (default: 700)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip requests whose output files already exist",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately on first error",
    )
    parser.add_argument(
        "--show-llm-io",
        action="store_true",
        help="Print baseline prompt and model output to console",
    )
    args = parser.parse_args()

    if args.show_llm_io:
        os.environ["LLM_ENABLE_CONSOLE_TRACE"] = "true"
        settings.LLM_ENABLE_CONSOLE_TRACE = True
        print("[INFO] Enabled LLM input/output console trace (--show-llm-io)")

    dataset_dir = Path(args.dataset_dir).resolve()
    results_root = Path(args.results_dir).resolve()

    if not dataset_dir.exists() or not dataset_dir.is_dir():
        print(f"[ERROR] dataset directory does not exist: {dataset_dir}")
        return 1

    model_overrides = _normalize_model_overrides(args.judge_models)
    if args.judge_model:
        model_overrides = _normalize_model_overrides([args.judge_model])
    if not model_overrides:
        model_overrides = [settings.DEFAULT_LLM_MODEL]

    criteria_for_dataset_json: list[dict[str, str]] | None = None
    if args.criteria_file:
        criteria_for_dataset_json = _load_criteria_from_file(Path(args.criteria_file).resolve())
    else:
        print("[INFO] --criteria-file not provided; extracting criteria from each source dataset json")

    fixed_batch_id: str | None = None
    if args.fixed_batch_id:
        candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", str(args.fixed_batch_id).strip()).strip("-._")
        fixed_batch_id = candidate or None

    final_exit_code = 0
    for judge_model in model_overrides:
        model_results_dir = results_root / _get_model_results_folder_name(judge_model)
        print(
            "[RUN] baseline=one_shot_prompt "
            f"judge_model={judge_model} "
            f"results_dir={model_results_dir} "
            f"json_pattern={args.json_pattern} "
            f"max_files={args.max_files} "
            f"request_max_concurrency={args.request_max_concurrency} "
            f"skip_existing={args.skip_existing}"
        )

        exit_code = asyncio.run(
            _run_batch_for_model(
                dataset_dir=dataset_dir,
                results_dir=model_results_dir,
                json_pattern=args.json_pattern,
                fail_fast=args.fail_fast,
                run_tag=args.run_tag,
                max_files=args.max_files,
                judge_model=judge_model,
                criteria_for_dataset_json=criteria_for_dataset_json,
                fixed_batch_id=fixed_batch_id,
                request_max_concurrency=args.request_max_concurrency,
                skip_existing=args.skip_existing,
                show_llm_io=args.show_llm_io,
                max_steps=args.max_steps,
                max_chars_per_field=args.max_chars_per_field,
            )
        )
        if exit_code != 0:
            final_exit_code = exit_code
            if args.fail_fast:
                break

    return final_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
