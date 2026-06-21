from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
import math
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
TECH_EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_TASK_GROUP_DATASET_DIR = TECH_EVAL_DIR / "dataset" / "dataset_grouped_by_task"
DEFAULT_TASK_GROUP_JSON_PATTERN = "**/*.json"
DEFAULT_OPENAI_JUDGE_MODEL = "gpt-5"
DEFAULT_DEEPSEEK_JUDGE_MODEL = "deepseek-chat"
DEFAULT_JUDGE_MODELS: Tuple[str, ...] = (
    DEFAULT_OPENAI_JUDGE_MODEL,
    DEFAULT_DEEPSEEK_JUDGE_MODEL,
)
RANKING_MODE_CRITERIA2 = "criteria2"
RANKING_MODE_BASELINE = "baseline"
DEFAULT_RANKING_MODES: Tuple[str, ...] = (
    RANKING_MODE_CRITERIA2,
    RANKING_MODE_BASELINE,
)
BASELINE_SYSTEM_PROMPT = (
    "You are a strict evaluator. Compare exactly two conditions and return ONLY valid JSON. "
    "Do not include markdown, prose, or code fences."
)


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


@dataclass
class DatasetItem:
    file_name: str
    file_path: Path
    condition_id: str
    task_raw: str
    task_label: str
    task_normalized: str
    task_group_id: str
    task_group_folder: str
    persona: str
    value: Optional[str]
    model: str


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _truncate_text(value: Any, max_chars: int = 320) -> str:
    text = _normalize_text(str(value or ""))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _safe_token(raw: str, fallback: str = "group") -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", str(raw or "").strip().lower())
    token = token.strip("._-")
    return token or fallback


def _normalize_model_name(raw_model: Optional[str]) -> Optional[str]:
    if raw_model is None:
        return None
    model_name = str(raw_model).strip()
    return model_name or None


def _split_judge_models(raw_values: Optional[Sequence[str]]) -> List[str]:
    models: List[str] = []
    seen: set[str] = set()

    for raw in raw_values or []:
        for token in re.split(r"[\s,]+", str(raw or "").strip()):
            model_name = _normalize_model_name(token)
            if not model_name or model_name in seen:
                continue
            seen.add(model_name)
            models.append(model_name)

    return models


def _resolve_judge_models(single_model: Optional[str], multi_models: Optional[Sequence[str]]) -> List[Optional[str]]:
    parsed_multi_models = _split_judge_models(multi_models)
    if parsed_multi_models:
        return parsed_multi_models

    normalized_single_model = _normalize_model_name(single_model)
    if normalized_single_model:
        return [normalized_single_model]

    return list(DEFAULT_JUDGE_MODELS)


def _normalize_ranking_mode(raw_mode: Optional[str]) -> Optional[str]:
    token = str(raw_mode or "").strip().lower()
    if not token:
        return None

    aliases = {
        "criteria": RANKING_MODE_CRITERIA2,
        "criteria2": RANKING_MODE_CRITERIA2,
        "prompted": RANKING_MODE_CRITERIA2,
        "baseline": RANKING_MODE_BASELINE,
        "direct": RANKING_MODE_BASELINE,
        "direct_compare": RANKING_MODE_BASELINE,
        "no_prompt": RANKING_MODE_BASELINE,
    }
    return aliases.get(token)


def _split_ranking_modes(raw_values: Optional[Sequence[str]]) -> List[str]:
    modes: List[str] = []
    seen: set[str] = set()

    for raw in raw_values or []:
        for token in re.split(r"[\s,]+", str(raw or "").strip()):
            mode = _normalize_ranking_mode(token)
            if not mode or mode in seen:
                continue
            seen.add(mode)
            modes.append(mode)

    return modes


def _resolve_ranking_modes(raw_values: Optional[Sequence[str]]) -> List[str]:
    parsed = _split_ranking_modes(raw_values)
    if parsed:
        return parsed
    return list(DEFAULT_RANKING_MODES)


def _judge_output_subdir_name(judge_model: Optional[str]) -> str:
    return _safe_token(judge_model or "default_judge", fallback="default_judge")


def _extract_task_name_and_url(task_raw: str, fallback_name: str) -> Tuple[str, str]:
    text = str(task_raw or "").strip()
    if not text:
        return fallback_name, ""

    url_match = re.search(r"https?://\S+", text)
    url = url_match.group(0).rstrip(".,)") if url_match else ""

    if url_match:
        text = text.replace(url_match.group(0), " ")

    text = _normalize_text(text)
    # Remove trailing connector words left after URL removal, e.g. "buy milk from <url>".
    text = re.sub(r"(?:\b(?:from|on|at)\s*)+$", "", text, flags=re.IGNORECASE).strip()

    return (text or fallback_name), url


def _normalize_task_for_group(task_raw: str, fallback_name: str) -> Tuple[str, str, str]:
    task_label, _ = _extract_task_name_and_url(task_raw, fallback_name)
    task_label = _normalize_text(task_label) or fallback_name
    task_normalized = _normalize_text(task_label).lower()
    task_group_id = _safe_token(task_normalized, fallback="task")
    return task_label, task_normalized, task_group_id


def _folder_grouping(dataset_dir: Path, json_file: Path, fallback_group_id: str) -> Tuple[str, str]:
    """Use folder as grouping key so each dataset subfolder becomes one pairwise group."""
    try:
        rel_parent = json_file.resolve().parent.relative_to(dataset_dir.resolve())
    except ValueError:
        rel_parent = json_file.resolve().parent

    rel_parent_str = str(rel_parent).replace("\\", "/").strip()
    if not rel_parent_str or rel_parent_str == ".":
        return fallback_group_id, ""

    folder_group_id = _safe_token(rel_parent_str.replace("/", "__"), fallback=fallback_group_id)
    return folder_group_id, rel_parent_str


def _infer_value_from_persona(persona: str) -> Optional[str]:
    text = str(persona or "")
    match = re.search(r"values?\s+([A-Za-z][A-Za-z_-]*)", text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip().lower()


def _load_dataset_items(dataset_dir: Path, json_pattern: str) -> List[DatasetItem]:
    items: List[DatasetItem] = []

    json_files = sorted(path for path in dataset_dir.glob(json_pattern) if path.is_file())
    for json_file in json_files:
        source = json.loads(json_file.read_text(encoding="utf-8"))
        if not isinstance(source, dict):
            continue

        fallback_name = json_file.stem
        task_raw = str(source.get("task") or fallback_name)
        task_label, task_normalized, task_group_id = _normalize_task_for_group(task_raw, fallback_name)
        folder_group_id, folder_relpath = _folder_grouping(dataset_dir, json_file, task_group_id)

        persona = str(source.get("persona") or "")
        value = _infer_value_from_persona(persona)

        items.append(
            DatasetItem(
                file_name=json_file.name,
                file_path=json_file.resolve(),
                condition_id=json_file.stem,
                task_raw=task_raw,
                task_label=task_label,
                task_normalized=task_normalized,
                task_group_id=folder_group_id,
                task_group_folder=folder_relpath,
                persona=persona,
                value=value,
                model=str(source.get("model") or ""),
            )
        )

    return items


def build_group_manifest(dataset_dir: Path, json_pattern: str) -> Dict[str, Any]:
    items = _load_dataset_items(dataset_dir, json_pattern)

    grouped: Dict[str, List[DatasetItem]] = {}
    for item in items:
        grouped.setdefault(item.task_group_id, []).append(item)

    groups_output: List[Dict[str, Any]] = []
    for group_id in sorted(grouped.keys()):
        members = sorted(grouped[group_id], key=lambda x: x.file_name)
        representative = members[0]
        groups_output.append(
            {
                "group_id": group_id,
                "task": representative.task_label,
                "task_normalized": representative.task_normalized,
                "group_folder": representative.task_group_folder,
                "size": len(members),
                "files": [
                    {
                        "file_name": item.file_name,
                        "file_path": str(item.file_path),
                        "condition_id": item.condition_id,
                        "persona": item.persona,
                        "value": item.value,
                        "model": item.model,
                    }
                    for item in members
                ],
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_dir": str(dataset_dir.resolve()),
        "json_pattern": json_pattern,
        "grouping_mode": "folder",
        "total_files": len(items),
        "group_count": len(groups_output),
        "groups": groups_output,
    }


def _materialize_group_folders(group_manifest: Dict[str, Any], output_dir: Path) -> None:
    if output_dir.exists() and output_dir.is_dir():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for group in group_manifest.get("groups", []):
        group_id = str(group.get("group_id") or "")
        if not group_id:
            continue

        group_dir = output_dir / group_id
        group_dir.mkdir(parents=True, exist_ok=True)

        for file_info in group.get("files", []):
            file_name = str(file_info.get("file_name") or "")
            file_path_raw = str(file_info.get("file_path") or "")
            if not file_name or not file_path_raw:
                continue

            source_path = Path(file_path_raw)
            if not source_path.exists() or not source_path.is_file():
                continue

            target_path = group_dir / file_name
            target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")


def _build_model_outputs(raw_steps: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_steps, list):
        return []

    model_outputs: List[Dict[str, Any]] = []
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

    return model_outputs


def _build_baseline_step_summaries(raw_steps: Any, max_steps: int = 12) -> List[Dict[str, Any]]:
    if not isinstance(raw_steps, list):
        return []

    summaries: List[Dict[str, Any]] = []
    for idx, step in enumerate(raw_steps):
        if not isinstance(step, dict):
            continue

        step_id = step.get("step_id") if _is_number(step.get("step_id")) else idx + 1
        summaries.append(
            {
                "step_id": int(step_id),
                "evaluation": _truncate_text(step.get("EVALUATION") or step.get("evaluation_previous_goal") or "", 220),
                "reasoning": _truncate_text(step.get("AI REASONING") or step.get("thinking") or step.get("thinking_process") or "", 360),
                "memory": _truncate_text(step.get("MEMORY") or step.get("memory") or "", 220),
                "next_goal": _truncate_text(step.get("TARGET OBJECTIVE") or step.get("next_goal") or "", 180),
                "action": _truncate_text(step.get("ACTION") if "ACTION" in step else step.get("action"), 260),
            }
        )

    if len(summaries) <= max_steps:
        return summaries

    kept = summaries[:max_steps]
    kept.append(
        {
            "step_id": -1,
            "note": f"truncated_{len(summaries) - max_steps}_steps",
        }
    )
    return kept


def _build_baseline_condition_input(
    source_path: Path,
    source_json: Dict[str, Any],
    condition_id: str,
    source_file: str,
) -> Dict[str, Any]:
    fallback_task_name = source_path.stem
    task_name, _ = _extract_task_name_and_url(str(source_json.get("task") or ""), fallback_task_name)
    persona = str(source_json.get("persona") or "")

    return {
        "condition_id": condition_id,
        "source_file": source_file,
        "task": task_name,
        "persona": persona,
        "value": _infer_value_from_persona(persona),
        "model": str(source_json.get("model") or ""),
        "final_result": _truncate_text(source_json.get("final_result") or "", 500),
        "steps": _build_baseline_step_summaries(source_json.get("steps")),
    }


def _import_baseline_llm_modules() -> Tuple[Any, Any, Any]:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from app.services.llm_factory import get_chat_llm  # pylint: disable=import-error
    from langchain_core.messages import HumanMessage, SystemMessage  # pylint: disable=import-error

    return get_chat_llm, HumanMessage, SystemMessage


def _build_baseline_pairwise_prompt(
    group_task: str,
    criterion_text: Optional[str],
    baseline_conditions: Sequence[Dict[str, Any]],
) -> str:
    condition_ids = [str(item.get("condition_id") or "") for item in baseline_conditions]
    criterion = _normalize_text(criterion_text or "")
    if not criterion:
        criterion = "Overall ranking quality: better task completion, stronger value alignment, and fewer unsupported assumptions."

    serialized_conditions = "\n\n".join(
        [
            f"Condition {idx}:\n{json.dumps(item, indent=2, ensure_ascii=False)}"
            for idx, item in enumerate(baseline_conditions, start=1)
        ]
    )

    return (
        f"Task: {_normalize_text(group_task)}\n"
        f"Criterion: {criterion}\n"
        f"Allowed condition_id values: {condition_ids}\n\n"
        "Return ONLY one JSON object with this exact top-level schema:\n"
        "{\n"
        '  "comparison_summary": "string",\n'
        '  "ranking": [\n'
        '    {"condition_id": "string", "rank": 1, "summary": "string", "confidence": 0.0, "evidence": ["string"]},\n'
        '    {"condition_id": "string", "rank": 2, "summary": "string", "confidence": 0.0, "evidence": ["string"]}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "1) Use each allowed condition_id exactly once.\n"
        "2) rank must be exactly 1 and 2 (no ties).\n"
        "3) confidence must be between 0 and 1.\n"
        "4) evidence items must be concrete observations from provided steps.\n\n"
        f"{serialized_conditions}\n"
    )


def _extract_llm_response_text(response: Any) -> str:
    content = getattr(response, "content", response)

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("output_text")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    parts.append(str(item))
                continue
            parts.append(str(item))
        return "\n".join(p for p in parts if p).strip()

    return str(content).strip()


def _extract_json_object_from_text(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("empty_baseline_response")

    candidates: List[str] = [text]
    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    candidates.extend(block.strip() for block in fenced_blocks if block.strip())

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        stripped = candidate.strip()
        for idx, ch in enumerate(stripped):
            if ch != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(stripped[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    raise ValueError("baseline_response_not_json_object")


def _normalize_baseline_ranking_rows(
    raw_ranking: Any,
    allowed_condition_ids: Sequence[str],
    condition_metadata: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    allowed_ids = [str(item).strip() for item in allowed_condition_ids if str(item).strip()]
    order_map = {cid: idx for idx, cid in enumerate(allowed_ids)}
    rows_by_condition: Dict[str, Dict[str, Any]] = {}

    for row in raw_ranking if isinstance(raw_ranking, list) else []:
        if not isinstance(row, dict):
            continue

        condition_id = str(row.get("condition_id") or "").strip()
        if not condition_id or condition_id not in order_map:
            continue

        raw_rank = row.get("rank")
        rank_value: Optional[int] = None
        if _is_number(raw_rank):
            rank_value = int(raw_rank)
        elif isinstance(raw_rank, str) and raw_rank.strip().isdigit():
            rank_value = int(raw_rank.strip())

        raw_confidence = row.get("confidence")
        confidence = 0.5
        if _is_number(raw_confidence):
            confidence = max(0.0, min(1.0, float(raw_confidence)))

        evidence_items: List[str] = []
        raw_evidence = row.get("evidence")
        if isinstance(raw_evidence, list):
            evidence_items = [_normalize_text(str(item)) for item in raw_evidence if _normalize_text(str(item))]
        elif raw_evidence is not None:
            evidence_text = _normalize_text(str(raw_evidence))
            if evidence_text:
                evidence_items = [evidence_text]

        meta = condition_metadata.get(condition_id, {})
        rank_sort = rank_value if rank_value is not None else 1000 + order_map[condition_id]
        rows_by_condition[condition_id] = {
            "_rank_sort": rank_sort,
            "condition_id": condition_id,
            "overall_assessment": str(row.get("overall_assessment") or "pass"),
            "confidence": confidence,
            "summary": _normalize_text(str(row.get("summary") or row.get("reason") or ""))
            or "Baseline direct prompt ranking.",
            "persona": str(meta.get("persona") or ""),
            "value": meta.get("value"),
            "model": str(meta.get("model") or ""),
            "run_index": int(meta.get("run_index") or 1),
            "evidence": evidence_items,
            "supporting_evidence": "\n".join(evidence_items) if evidence_items else None,
        }

    for condition_id in allowed_ids:
        if condition_id in rows_by_condition:
            continue
        meta = condition_metadata.get(condition_id, {})
        rows_by_condition[condition_id] = {
            "_rank_sort": 2000 + order_map[condition_id],
            "condition_id": condition_id,
            "overall_assessment": "pass",
            "confidence": 0.5,
            "summary": "Fallback ranking due to missing or unparsable baseline response row.",
            "persona": str(meta.get("persona") or ""),
            "value": meta.get("value"),
            "model": str(meta.get("model") or ""),
            "run_index": int(meta.get("run_index") or 1),
            "evidence": [],
            "supporting_evidence": None,
        }

    ordered = sorted(rows_by_condition.values(), key=lambda item: (item.get("_rank_sort", 9999), item["condition_id"]))
    normalized_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(ordered, start=1):
        row_copy = copy.deepcopy(row)
        row_copy.pop("_rank_sort", None)
        row_copy["rank"] = idx
        normalized_rows.append(row_copy)

    return normalized_rows


async def _run_baseline_pairwise_ranking(
    baseline_conditions: Sequence[Dict[str, Any]],
    judge_model: Optional[str],
    group_task: str,
    criterion_text: Optional[str],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if len(baseline_conditions) != 2:
        raise ValueError("baseline_requires_exactly_2_conditions")

    get_chat_llm, HumanMessage, SystemMessage = _import_baseline_llm_modules()

    resolved_model = _normalize_model_name(judge_model) or DEFAULT_OPENAI_JUDGE_MODEL
    llm = get_chat_llm(model=resolved_model, temperature=0.0)
    prompt = _build_baseline_pairwise_prompt(group_task, criterion_text, baseline_conditions)

    response = await llm.ainvoke(
        [
            SystemMessage(content=BASELINE_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
    )

    response_text = _extract_llm_response_text(response)
    parsed_response: Dict[str, Any] = {}
    try:
        parsed_response = _extract_json_object_from_text(response_text)
    except ValueError:
        parsed_response = {}

    allowed_condition_ids = [str(item.get("condition_id") or "") for item in baseline_conditions]
    condition_metadata = {
        str(item.get("condition_id") or ""): {
            "persona": item.get("persona"),
            "value": item.get("value"),
            "model": item.get("model"),
            "run_index": 1,
        }
        for item in baseline_conditions
    }
    ranking_rows = _normalize_baseline_ranking_rows(
        raw_ranking=parsed_response.get("ranking"),
        allowed_condition_ids=allowed_condition_ids,
        condition_metadata=condition_metadata,
    )

    best_condition_id = ranking_rows[0]["condition_id"] if ranking_rows else ""
    comparison_summary = _normalize_text(str(parsed_response.get("comparison_summary") or ""))
    if not comparison_summary:
        comparison_summary = "Baseline direct prompt comparison."

    result_payload = {
        "baseline_prompt_evaluation": {
            "mode": "baseline_direct_prompt",
            "judge_model": resolved_model,
            "criterion": _normalize_text(criterion_text or "") or None,
            "group_task": _normalize_text(group_task),
            "condition_ids": allowed_condition_ids,
            "raw_response_text": response_text,
            "parsed_response": parsed_response,
        },
        "multi_condition_assessment": {
            "comparison_timestamp": datetime.now().isoformat(),
            "total_conditions": len(ranking_rows),
            "criteria_comparisons": [
                {
                    "title": "baseline_direct_prompt",
                    "assertion": _normalize_text(criterion_text or ""),
                    "description": "Direct pairwise ranking baseline prompt.",
                    "condition_comparison": {
                        "best_condition_id": best_condition_id,
                        "best_condition_rank": 1,
                        "ranking": ranking_rows,
                        "ranking_reasoning": comparison_summary,
                        "comparison_summary": comparison_summary,
                    },
                }
            ],
        },
    }

    return result_payload, ranking_rows


def _normalize_dataset_json_to_run_payload(source_file: Path, source_json: Dict[str, Any]) -> Dict[str, Any]:
    fallback_task_name = source_file.stem
    task_name, task_url = _extract_task_name_and_url(str(source_json.get("task") or ""), fallback_task_name)
    persona = str(source_json.get("persona") or "").strip()
    value = _infer_value_from_persona(persona)

    model_outputs = _build_model_outputs(source_json.get("steps"))

    run_payload = {
        "metadata": {
            "timestamp_utc": datetime.now().isoformat(),
            "task": {
                "name": task_name,
                "url": task_url,
            },
            "persona": persona,
            "model": str(source_json.get("model") or ""),
            "value": value,
            "run_index": 1,
            "id": source_file.stem,
        },
        "summary": {
            "is_done": bool(model_outputs),
            "is_successful": bool(model_outputs),
            "has_errors": False,
            "number_of_steps": len(model_outputs),
            "total_duration_seconds": None,
            "final_result": str(source_json.get("final_result") or ""),
            "error_message": None,
        },
        "details": {
            "screenshots": [],
            "model_outputs": model_outputs,
            "last_action": model_outputs[-1].get("action") if model_outputs else None,
            "structured_output": None,
        },
    }

    return run_payload


def _import_judge_modules() -> Tuple[Any, Any, Any]:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from app.api.deps import get_judge_services  # pylint: disable=import-error
    from app.api.judge import evaluate_experiment  # pylint: disable=import-error
    from app.schemas.judge import ExperimentEvaluationRequest  # pylint: disable=import-error

    return get_judge_services, evaluate_experiment, ExperimentEvaluationRequest


async def _run_single_llm_request(
    request_payload: Dict[str, Any],
    get_judge_services: Any,
    evaluate_experiment: Any,
    ExperimentEvaluationRequest: Any,
) -> Dict[str, Any]:
    request = ExperimentEvaluationRequest.model_validate(request_payload)
    services = get_judge_services()
    response = await evaluate_experiment(request, services)
    return response.model_dump(mode="json")


def _build_condition_to_file_map(group: Dict[str, Any]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for file_info in group.get("files", []):
        file_name = str(file_info.get("file_name") or "")
        file_path_raw = str(file_info.get("file_path") or "")
        if file_name:
            mapping[file_name] = file_name
        if file_path_raw:
            mapping[file_path_raw] = file_name or file_path_raw
            path_obj = Path(file_path_raw)
            mapping[str(path_obj)] = file_name or str(path_obj)
            mapping[str(path_obj.resolve())] = file_name or str(path_obj.resolve())
    return mapping


def _extract_primary_ranking(result_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    multi = result_payload.get("multi_condition_assessment")
    if not isinstance(multi, dict):
        return []

    criteria_comparisons = multi.get("criteria_comparisons")
    if not isinstance(criteria_comparisons, list) or not criteria_comparisons:
        return []

    first_comparison = criteria_comparisons[0]
    if not isinstance(first_comparison, dict):
        return []

    condition_comparison = first_comparison.get("condition_comparison")
    if not isinstance(condition_comparison, dict):
        return []

    ranking = condition_comparison.get("ranking")
    if not isinstance(ranking, list):
        return []

    return [item for item in ranking if isinstance(item, dict)]


def _prepare_group_run_payload(
    group: Dict[str, Any],
    normalized_dir: Path,
    criteria2_text: Optional[str],
    ranking_mode: str,
    judge_model: Optional[str],
) -> Tuple[Dict[str, Any], Dict[str, str], str, List[Dict[str, Any]]]:
    normalized_dir.mkdir(parents=True, exist_ok=True)

    conditions: List[Dict[str, str]] = []
    condition_to_source: Dict[str, str] = {}
    criteria2_candidates: set[str] = set()
    baseline_conditions: List[Dict[str, Any]] = []

    for file_info in group.get("files", []):
        file_path_raw = str(file_info.get("file_path") or "")
        file_name = str(file_info.get("file_name") or "")
        if not file_path_raw or not file_name:
            continue

        source_path = Path(file_path_raw)
        if not source_path.exists() or not source_path.is_file():
            continue

        source_json = json.loads(source_path.read_text(encoding="utf-8"))
        if not isinstance(source_json, dict):
            continue

        source_criteria2 = _normalize_text(
            str(source_json.get("criteria2") or source_json.get("criteria_2") or "")
        )
        if source_criteria2:
            criteria2_candidates.add(source_criteria2)

        run_payload = _normalize_dataset_json_to_run_payload(source_path, source_json)
        normalized_path = normalized_dir / f"{source_path.stem}__normalized.json"
        normalized_path.write_text(json.dumps(run_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        condition_id = str(normalized_path.resolve())
        conditions.append({"conditionID": condition_id})
        condition_to_source[condition_id] = file_name
        baseline_conditions.append(
            _build_baseline_condition_input(
                source_path=source_path,
                source_json=source_json,
                condition_id=condition_id,
                source_file=file_name,
            )
        )

    effective_criteria2 = _normalize_text(criteria2_text or "")
    criterion_title = "criteria2"
    criterion_assertion = ""
    criterion_description = ""

    # Baseline and criteria2 modes both use criteria2 as the ranking assertion.
    if not effective_criteria2:
        if len(criteria2_candidates) > 1:
            raise ValueError("multiple_criteria2_in_group")
        if criteria2_candidates:
            effective_criteria2 = next(iter(criteria2_candidates))

    if not effective_criteria2:
        raise ValueError("missing_criteria2")

    criterion_assertion = effective_criteria2
    criterion_description = "User-provided criteria2 for same-task condition ranking."

    payload: Dict[str, Any] = {
        "conditions": conditions,
        "criteria": [
            {
                "title": criterion_title,
                "assertion": criterion_assertion,
                "description": criterion_description,
            }
        ],
    }
    if judge_model:
        payload["judge_model"] = judge_model

    return payload, condition_to_source, effective_criteria2, baseline_conditions


def _load_manifest_or_build(dataset_dir: Path, json_pattern: str, groups_file: Optional[Path]) -> Dict[str, Any]:
    if groups_file is None:
        return build_group_manifest(dataset_dir, json_pattern)

    parsed = json.loads(groups_file.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or "groups" not in parsed:
        raise ValueError(f"Invalid groups manifest: {groups_file}")
    return parsed


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _rank_from_scores_desc(scores: Dict[str, float]) -> Dict[str, float]:
    ordered = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    ranks: Dict[str, float] = {}

    index = 0
    while index < len(ordered):
        same_score = [ordered[index]]
        j = index + 1
        while j < len(ordered) and ordered[j][1] == ordered[index][1]:
            same_score.append(ordered[j])
            j += 1

        start_rank = index + 1
        end_rank = index + len(same_score)
        avg_rank = (start_rank + end_rank) / 2.0
        for key, _ in same_score:
            ranks[key] = avg_rank

        index = j

    return ranks


def _ranking_list_to_ranks(ranking_list: Sequence[str]) -> Dict[str, float]:
    ranks: Dict[str, float] = {}
    for idx, item in enumerate(ranking_list, start=1):
        key = str(item).strip()
        if key and key not in ranks:
            ranks[key] = float(idx)
    return ranks


def _prepare_human_ranks_for_group(
    human_group: Dict[str, Any],
    expected_items: Sequence[str],
) -> Dict[str, float]:
    expected_set = set(expected_items)

    ranking = human_group.get("ranking")
    if isinstance(ranking, list):
        raw_ranks = _ranking_list_to_ranks([str(x) for x in ranking])
        return {k: v for k, v in raw_ranks.items() if k in expected_set}

    scores = human_group.get("scores")
    if isinstance(scores, dict):
        numeric_scores = {
            str(k): float(v)
            for k, v in scores.items()
            if str(k) in expected_set and _is_number(v)
        }
        if numeric_scores:
            return _rank_from_scores_desc(numeric_scores)

    items = human_group.get("items")
    if isinstance(items, list):
        rank_map: Dict[str, float] = {}
        score_map: Dict[str, float] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("file_name") or item.get("condition_id") or "").strip()
            if not item_id or item_id not in expected_set:
                continue

            human_rank = item.get("human_rank")
            if _is_number(human_rank):
                rank_map[item_id] = float(human_rank)

            human_score = item.get("human_score")
            if _is_number(human_score):
                score_map[item_id] = float(human_score)

        if rank_map:
            return rank_map
        if score_map:
            return _rank_from_scores_desc(score_map)

    return {}


def _spearman_rho(rank_x: Sequence[float], rank_y: Sequence[float]) -> Optional[float]:
    n = len(rank_x)
    if n < 2:
        return None

    denom = n * (n * n - 1)
    if denom == 0:
        return None

    d2_sum = 0.0
    for x, y in zip(rank_x, rank_y):
        d = x - y
        d2_sum += d * d

    return 1.0 - (6.0 * d2_sum / float(denom))


def _kendall_tau_b(rank_x: Sequence[float], rank_y: Sequence[float]) -> Optional[float]:
    n = len(rank_x)
    if n < 2:
        return None

    concordant = 0
    discordant = 0
    ties_x = 0
    ties_y = 0

    for i in range(n):
        for j in range(i + 1, n):
            dx = rank_x[i] - rank_x[j]
            dy = rank_y[i] - rank_y[j]

            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                ties_x += 1
                continue
            if dy == 0:
                ties_y += 1
                continue

            if dx * dy > 0:
                concordant += 1
            else:
                discordant += 1

    numerator = concordant - discordant
    denom = math.sqrt((concordant + discordant + ties_x) * (concordant + discordant + ties_y))
    if denom == 0:
        return None

    return numerator / denom


def compute_inter_agreement(llm_ranking_file: Path, human_ranking_file: Path, output_file: Optional[Path]) -> Dict[str, Any]:
    llm_data = json.loads(llm_ranking_file.read_text(encoding="utf-8"))
    human_data = json.loads(human_ranking_file.read_text(encoding="utf-8"))

    if not isinstance(llm_data, dict) or not isinstance(human_data, dict):
        raise ValueError("llm/human ranking files must be JSON objects")

    llm_groups = llm_data.get("groups", [])
    human_groups = human_data.get("groups", [])
    if not isinstance(llm_groups, list) or not isinstance(human_groups, list):
        raise ValueError("Both llm and human files must include a groups list")

    human_map: Dict[str, Dict[str, Any]] = {}
    for group in human_groups:
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("group_id") or "").strip()
        if group_id:
            human_map[group_id] = group

    group_metrics: List[Dict[str, Any]] = []
    rho_values: List[float] = []
    tau_values: List[float] = []
    top1_matches = 0
    compared_groups = 0

    for llm_group in llm_groups:
        if not isinstance(llm_group, dict):
            continue

        group_id = str(llm_group.get("group_id") or "").strip()
        if not group_id:
            continue

        llm_ranking = llm_group.get("ranking", [])
        if not isinstance(llm_ranking, list):
            continue

        llm_rank_map: Dict[str, float] = {}
        for row in llm_ranking:
            if not isinstance(row, dict):
                continue
            file_name = str(row.get("source_file") or row.get("condition_id") or "").strip()
            rank_value = row.get("rank")
            if file_name and _is_number(rank_value):
                llm_rank_map[file_name] = float(rank_value)

        if len(llm_rank_map) < 2:
            continue

        human_group = human_map.get(group_id)
        if human_group is None:
            group_metrics.append(
                {
                    "group_id": group_id,
                    "status": "missing_human_group",
                    "reason": "No human group found with same group_id",
                }
            )
            continue

        human_rank_map = _prepare_human_ranks_for_group(human_group, llm_rank_map.keys())

        common_items = sorted(set(llm_rank_map.keys()) & set(human_rank_map.keys()))
        if len(common_items) < 2:
            group_metrics.append(
                {
                    "group_id": group_id,
                    "status": "insufficient_overlap",
                    "reason": "Need at least 2 overlapping items between llm and human rankings",
                    "llm_items": sorted(llm_rank_map.keys()),
                    "human_items": sorted(human_rank_map.keys()),
                }
            )
            continue

        llm_ranks = [llm_rank_map[item] for item in common_items]
        human_ranks = [human_rank_map[item] for item in common_items]

        rho = _spearman_rho(llm_ranks, human_ranks)
        tau = _kendall_tau_b(llm_ranks, human_ranks)

        compared_groups += 1
        if rho is not None:
            rho_values.append(rho)
        if tau is not None:
            tau_values.append(tau)

        llm_top = min(common_items, key=lambda item: llm_rank_map[item])
        human_top = min(common_items, key=lambda item: human_rank_map[item])
        top1_match = llm_top == human_top
        if top1_match:
            top1_matches += 1

        group_metrics.append(
            {
                "group_id": group_id,
                "status": "ok",
                "n_items": len(common_items),
                "spearman_rho": rho,
                "kendall_tau_b": tau,
                "top1_match": top1_match,
                "llm_top1": llm_top,
                "human_top1": human_top,
                "items": [
                    {
                        "item": item,
                        "llm_rank": llm_rank_map[item],
                        "human_rank": human_rank_map[item],
                    }
                    for item in common_items
                ],
            }
        )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "llm_ranking_file": str(llm_ranking_file.resolve()),
        "human_ranking_file": str(human_ranking_file.resolve()),
        "groups_total": len(llm_groups),
        "groups_compared": compared_groups,
        "spearman_mean": (sum(rho_values) / len(rho_values)) if rho_values else None,
        "kendall_tau_b_mean": (sum(tau_values) / len(tau_values)) if tau_values else None,
        "top1_agreement_rate": (top1_matches / compared_groups) if compared_groups > 0 else None,
        "group_metrics": group_metrics,
    }

    if output_file is not None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return report


async def run_llm_group_ranking(
    dataset_dir: Path,
    json_pattern: str,
    groups_file: Optional[Path],
    output_dir: Path,
    criteria2_text: Optional[str],
    ranking_mode: str,
    judge_model: Optional[str],
    min_group_size: int,
) -> Dict[str, Any]:
    group_manifest = _load_manifest_or_build(dataset_dir, json_pattern, groups_file)
    groups = group_manifest.get("groups", [])
    if not isinstance(groups, list):
        raise ValueError("groups manifest must include a groups list")

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_token = _safe_token(ranking_mode, fallback="mode")
    run_output_dir = output_dir / f"task_group_ranking_{mode_token}_{batch_id}"
    run_output_dir.mkdir(parents=True, exist_ok=True)

    normalized_root = run_output_dir / "_normalized"
    raw_root = run_output_dir / "raw"
    normalized_root.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)
    judge_module_bundle: Optional[Tuple[Any, Any, Any]] = None

    output_groups: List[Dict[str, Any]] = []
    skipped_groups: List[Dict[str, Any]] = []

    for group in groups:
        if not isinstance(group, dict):
            continue

        group_id = str(group.get("group_id") or "").strip()
        task = str(group.get("task") or "").strip()
        files = group.get("files", [])
        if not group_id or not isinstance(files, list):
            continue

        if len(files) != 2:
            skipped_groups.append(
                {
                    "group_id": group_id,
                    "task": task,
                    "reason": "group_size_ne_2",
                    "size": len(files),
                }
            )
            continue

        if len(files) < max(2, int(min_group_size)):
            skipped_groups.append(
                {
                    "group_id": group_id,
                    "task": task,
                    "reason": f"group_size_lt_{max(2, int(min_group_size))}",
                    "size": len(files),
                }
            )
            continue

        group_norm_dir = normalized_root / group_id
        try:
            payload, condition_to_source, group_criteria2, baseline_conditions = _prepare_group_run_payload(
                group=group,
                normalized_dir=group_norm_dir,
                criteria2_text=criteria2_text,
                ranking_mode=ranking_mode,
                judge_model=judge_model,
            )
        except ValueError as exc:
            skipped_groups.append(
                {
                    "group_id": group_id,
                    "task": task,
                    "reason": str(exc),
                    "size": len(files),
                }
            )
            continue

        if len(payload.get("conditions", [])) != 2:
            skipped_groups.append(
                {
                    "group_id": group_id,
                    "task": task,
                    "reason": "usable_conditions_ne_2",
                    "size": len(payload.get("conditions", [])),
                }
            )
            continue

        if ranking_mode == RANKING_MODE_BASELINE:
            result_payload, ranking_rows = await _run_baseline_pairwise_ranking(
                baseline_conditions=baseline_conditions,
                judge_model=judge_model,
                group_task=task,
                criterion_text=group_criteria2,
            )
        else:
            if judge_module_bundle is None:
                judge_module_bundle = _import_judge_modules()
            get_judge_services, evaluate_experiment, ExperimentEvaluationRequest = judge_module_bundle

            result_payload = await _run_single_llm_request(
                request_payload=payload,
                get_judge_services=get_judge_services,
                evaluate_experiment=evaluate_experiment,
                ExperimentEvaluationRequest=ExperimentEvaluationRequest,
            )

            ranking_rows = _extract_primary_ranking(result_payload)
        condition_file_map = _build_condition_to_file_map(group)

        transformed_ranking = []
        for row in ranking_rows:
            condition_id = str(row.get("condition_id") or "").strip()
            source_file = condition_to_source.get(condition_id) or condition_file_map.get(condition_id) or condition_id
            transformed_row = copy.deepcopy(row)
            transformed_row["source_file"] = source_file
            transformed_ranking.append(transformed_row)

        raw_result_path = raw_root / f"{group_id}__llm_result.json"
        raw_result_path.write_text(json.dumps(result_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        output_groups.append(
            {
                "group_id": group_id,
                "task": task,
                "ranking_mode": ranking_mode,
                "criteria2": group_criteria2,
                "size": len(payload.get("conditions", [])),
                "ranking": transformed_ranking,
                "raw_result_file": str(raw_result_path.resolve()),
            }
        )

    llm_summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_dir": str(dataset_dir.resolve()),
        "groups_file": str(groups_file.resolve()) if groups_file else None,
        "ranking_mode": ranking_mode,
        "pairwise_only": True,
        "criteria2": _normalize_text(criteria2_text or "") or None,
        "judge_model": judge_model,
        "group_count_total": len(groups),
        "group_count_evaluated": len(output_groups),
        "group_count_skipped": len(skipped_groups),
        "groups": output_groups,
        "skipped_groups": skipped_groups,
    }

    llm_summary_path = run_output_dir / "llm_group_ranking.json"
    llm_summary_path.write_text(json.dumps(llm_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    human_template = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "based_on_llm_file": str(llm_summary_path.resolve()),
        "criteria2": _normalize_text(criteria2_text or "") or None,
        "groups": [
            {
                "group_id": group["group_id"],
                "task": group["task"],
                "ranking_mode": group.get("ranking_mode"),
                "criteria2": group.get("criteria2"),
                "ranking": [row.get("source_file") for row in group.get("ranking", [])],
                "items": [
                    {
                        "file_name": row.get("source_file"),
                        "human_rank": None,
                        "human_score": None,
                        "comment": "",
                    }
                    for row in group.get("ranking", [])
                ],
            }
            for group in output_groups
        ],
    }

    human_template_path = run_output_dir / "human_ranking_template.json"
    human_template_path.write_text(json.dumps(human_template, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "run_output_dir": str(run_output_dir.resolve()),
        "llm_summary_file": str(llm_summary_path.resolve()),
        "human_template_file": str(human_template_path.resolve()),
        "llm_summary": llm_summary,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run pairwise ranking for dataset subfolders (2 JSON files per folder)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    group_parser = subparsers.add_parser("group", help="Build task group manifest from dataset JSON files")
    group_parser.add_argument(
        "--dataset-dir",
        default=str(DEFAULT_TASK_GROUP_DATASET_DIR),
        help="Dataset root directory (default: technical_evaluation/dataset/dataset_grouped_by_task)",
    )
    group_parser.add_argument(
        "--json-pattern",
        default=DEFAULT_TASK_GROUP_JSON_PATTERN,
        help="JSON glob pattern (default: **/*.json)",
    )
    group_parser.add_argument(
        "--output-file",
        default=str(TECH_EVAL_DIR / "results" / "task_groups_latest.json"),
        help="Output file for group manifest",
    )
    group_parser.add_argument(
        "--materialize-dir",
        default=None,
        help="Optional directory to copy grouped JSON files into per-task subfolders",
    )

    llm_parser = subparsers.add_parser("llm-rank", help="Run criteria2 ranking within each task group")
    llm_parser.add_argument(
        "--dataset-dir",
        default=str(DEFAULT_TASK_GROUP_DATASET_DIR),
        help="Dataset directory (default: technical_evaluation/dataset/dataset_grouped_by_task)",
    )
    llm_parser.add_argument(
        "--json-pattern",
        default=DEFAULT_TASK_GROUP_JSON_PATTERN,
        help="JSON glob pattern (default: **/*.json)",
    )
    llm_parser.add_argument("--groups-file", default=None, help="Optional existing group manifest JSON")
    llm_parser.add_argument(
        "--output-dir",
        default=str(TECH_EVAL_DIR / "results"),
        help="Output directory for ranking run outputs",
    )
    llm_parser.add_argument(
        "--criteria2-text",
        default=None,
        help="Optional criteria2 assertion override. If omitted, read criteria2 from dataset JSON files in each group.",
    )
    llm_parser.add_argument(
        "--judge-model",
        default=None,
        help=f"Optional judge model override (default run set: {', '.join(DEFAULT_JUDGE_MODELS)})",
    )
    llm_parser.add_argument(
        "--judge-models",
        nargs="+",
        default=None,
        help="Optional list of judge models (supports space- or comma-separated values). Overrides --judge-model.",
    )
    llm_parser.add_argument(
        "--run-modes",
        nargs="+",
        default=None,
        help="Ranking modes to run: criteria2, baseline (default runs both)",
    )
    llm_parser.add_argument("--min-group-size", type=int, default=2, help="Minimum group size to evaluate")

    agreement_parser = subparsers.add_parser("inter-agreement", help="Compute inter-agreement between LLM and human rankings")
    agreement_parser.add_argument("--llm-ranking-file", required=True, help="LLM ranking summary JSON file")
    agreement_parser.add_argument("--human-ranking-file", required=True, help="Human ranking JSON file")
    agreement_parser.add_argument("--output-file", default=None, help="Optional output JSON file for agreement report")

    full_parser = subparsers.add_parser("full", help="Run group build + llm ranking + optional agreement")
    full_parser.add_argument(
        "--dataset-dir",
        default=str(DEFAULT_TASK_GROUP_DATASET_DIR),
        help="Dataset directory (default: technical_evaluation/dataset/dataset_grouped_by_task)",
    )
    full_parser.add_argument(
        "--json-pattern",
        default=DEFAULT_TASK_GROUP_JSON_PATTERN,
        help="JSON glob pattern (default: **/*.json)",
    )
    full_parser.add_argument(
        "--output-dir",
        default=str(TECH_EVAL_DIR / "results"),
        help="Output directory for full run outputs",
    )
    full_parser.add_argument(
        "--criteria2-text",
        default=None,
        help="Optional criteria2 assertion override. If omitted, read criteria2 from dataset JSON files in each group.",
    )
    full_parser.add_argument(
        "--judge-model",
        default=None,
        help=f"Optional judge model override (default run set: {', '.join(DEFAULT_JUDGE_MODELS)})",
    )
    full_parser.add_argument(
        "--judge-models",
        nargs="+",
        default=None,
        help="Optional list of judge models (supports space- or comma-separated values). Overrides --judge-model.",
    )
    full_parser.add_argument(
        "--run-modes",
        nargs="+",
        default=None,
        help="Ranking modes to run: criteria2, baseline (default runs both)",
    )
    full_parser.add_argument("--min-group-size", type=int, default=2, help="Minimum group size to evaluate")
    full_parser.add_argument("--human-ranking-file", default=None, help="Optional human ranking file for agreement")

    raw_argv = sys.argv[1:]
    known_commands = {"group", "llm-rank", "inter-agreement", "full"}
    needs_default_command = bool(raw_argv) and raw_argv[0] not in known_commands and raw_argv[0] not in {"-h", "--help"}

    if not raw_argv:
        print("[INFO] No command specified; defaulting to 'full'")
        return parser.parse_args(["full"])

    if needs_default_command:
        print("[INFO] No command specified; defaulting to 'full'")
        return parser.parse_args(["full", *raw_argv])

    return parser.parse_args(raw_argv)


def main() -> int:
    args = _parse_args()

    if args.command == "group":
        dataset_dir = Path(args.dataset_dir).resolve()
        output_file = Path(args.output_file).resolve()

        manifest = build_group_manifest(dataset_dir, args.json_pattern)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        materialize_dir_raw = getattr(args, "materialize_dir", None)
        if materialize_dir_raw:
            materialize_dir = Path(materialize_dir_raw).resolve()
            _materialize_group_folders(manifest, materialize_dir)
            print(f"[DONE] Materialized grouped files under: {materialize_dir}")

        print(f"[DONE] Group manifest written: {output_file}")
        print(f"[DONE] total_files={manifest.get('total_files')} groups={manifest.get('group_count')}")
        return 0

    if args.command == "llm-rank":
        dataset_dir = Path(args.dataset_dir).resolve()
        groups_file = Path(args.groups_file).resolve() if args.groups_file else None
        output_dir = Path(args.output_dir).resolve()

        judge_models = _resolve_judge_models(args.judge_model, getattr(args, "judge_models", None))
        ranking_modes = _resolve_ranking_modes(getattr(args, "run_modes", None))
        multi_model_mode = len(judge_models) > 1
        multi_mode_run = len(ranking_modes) > 1

        for judge_model in judge_models:
            model_output_dir = output_dir
            if multi_model_mode:
                model_output_dir = output_dir / _judge_output_subdir_name(judge_model)

            for ranking_mode in ranking_modes:
                run_output_root = model_output_dir
                if multi_mode_run:
                    run_output_root = model_output_dir / _safe_token(ranking_mode, fallback="mode")

                result = asyncio.run(
                    run_llm_group_ranking(
                        dataset_dir=dataset_dir,
                        json_pattern=args.json_pattern,
                        groups_file=groups_file,
                        output_dir=run_output_root,
                        criteria2_text=args.criteria2_text,
                        ranking_mode=ranking_mode,
                        judge_model=judge_model,
                        min_group_size=args.min_group_size,
                    )
                )

                print(f"[DONE] Judge model: {judge_model or 'default'}")
                print(f"[DONE] Ranking mode: {ranking_mode}")
                print(f"[DONE] LLM ranking output dir: {result['run_output_dir']}")
                print(f"[DONE] LLM ranking summary: {result['llm_summary_file']}")
                print(f"[DONE] Human template: {result['human_template_file']}")

        if multi_model_mode:
            print(f"[DONE] Multi-model output root: {output_dir}")
        if multi_mode_run:
            print(f"[DONE] Multi-mode run completed: {', '.join(ranking_modes)}")
        return 0

    if args.command == "inter-agreement":
        llm_file = Path(args.llm_ranking_file).resolve()
        human_file = Path(args.human_ranking_file).resolve()
        output_file = Path(args.output_file).resolve() if args.output_file else None

        report = compute_inter_agreement(
            llm_ranking_file=llm_file,
            human_ranking_file=human_file,
            output_file=output_file,
        )

        if output_file is not None:
            print(f"[DONE] Inter-agreement report: {output_file}")
        print(
            "[DONE] groups_compared={} spearman_mean={} kendall_tau_b_mean={} top1_agreement_rate={}".format(
                report.get("groups_compared"),
                report.get("spearman_mean"),
                report.get("kendall_tau_b_mean"),
                report.get("top1_agreement_rate"),
            )
        )
        return 0

    if args.command == "full":
        dataset_dir = Path(args.dataset_dir).resolve()
        output_dir = Path(args.output_dir).resolve()

        judge_models = _resolve_judge_models(args.judge_model, getattr(args, "judge_models", None))
        ranking_modes = _resolve_ranking_modes(getattr(args, "run_modes", None))
        multi_model_mode = len(judge_models) > 1
        multi_mode_run = len(ranking_modes) > 1

        for judge_model in judge_models:
            model_output_dir = output_dir
            if multi_model_mode:
                model_output_dir = output_dir / _judge_output_subdir_name(judge_model)

            for ranking_mode in ranking_modes:
                run_output_root = model_output_dir
                if multi_mode_run:
                    run_output_root = model_output_dir / _safe_token(ranking_mode, fallback="mode")

                llm_result = asyncio.run(
                    run_llm_group_ranking(
                        dataset_dir=dataset_dir,
                        json_pattern=args.json_pattern,
                        groups_file=None,
                        output_dir=run_output_root,
                        criteria2_text=args.criteria2_text,
                        ranking_mode=ranking_mode,
                        judge_model=judge_model,
                        min_group_size=args.min_group_size,
                    )
                )

                print(f"[DONE] Judge model: {judge_model or 'default'}")
                print(f"[DONE] Ranking mode: {ranking_mode}")
                print(f"[DONE] LLM ranking summary: {llm_result['llm_summary_file']}")
                print(f"[DONE] Human template: {llm_result['human_template_file']}")

                human_ranking_raw = getattr(args, "human_ranking_file", None)
                if human_ranking_raw:
                    human_file = Path(human_ranking_raw).resolve()
                    agreement_path = Path(llm_result["run_output_dir"]).resolve() / "inter_agreement.json"
                    report = compute_inter_agreement(
                        llm_ranking_file=Path(llm_result["llm_summary_file"]).resolve(),
                        human_ranking_file=human_file,
                        output_file=agreement_path,
                    )
                    print(f"[DONE] Inter-agreement report: {agreement_path}")
                    print(
                        "[DONE] groups_compared={} spearman_mean={} kendall_tau_b_mean={} top1_agreement_rate={}".format(
                            report.get("groups_compared"),
                            report.get("spearman_mean"),
                            report.get("kendall_tau_b_mean"),
                            report.get("top1_agreement_rate"),
                        )
                    )

        if multi_model_mode:
            print(f"[DONE] Multi-model output root: {output_dir}")
        if multi_mode_run:
            print(f"[DONE] Multi-mode run completed: {', '.join(ranking_modes)}")

        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
