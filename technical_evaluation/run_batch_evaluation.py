from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.deps import get_judge_services
from app.api.judge import evaluate_experiment
from app.schemas.judge import ExperimentEvaluationRequest


@dataclass
class RequestParseResult:
    payloads: List[dict[str, Any]]
    warnings: List[str]


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


async def run_single_request(payload: dict[str, Any]) -> dict[str, Any]:
    request = ExperimentEvaluationRequest.model_validate(payload)
    services = get_judge_services()
    response = await evaluate_experiment(request, services)
    return response.model_dump(mode="json")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


async def run_batch(
    dataset_dir: Path,
    results_dir: Path,
    pattern: str,
    fail_fast: bool,
    forced_granularity: str | None,
    run_tag: str | None,
) -> int:
    results_dir.mkdir(parents=True, exist_ok=True)

    txt_files = sorted(dataset_dir.glob(pattern))
    if not txt_files:
        print(f"[WARN] No matching files in dataset directory: {dataset_dir} / {pattern}")
        return 1

    batch_id = _timestamp()
    summary: dict[str, Any] = {
        "batch_id": batch_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_dir": str(dataset_dir),
        "results_dir": str(results_dir),
        "forced_granularity": forced_granularity,
        "run_tag": run_tag,
        "files": [],
    }

    total_requests = 0
    success_requests = 0

    for txt_file in txt_files:
        file_result: dict[str, Any] = {
            "file": txt_file.name,
            "status": "ok",
            "warnings": [],
            "requests": [],
        }

        try:
            parse_result = parse_requests_from_txt(txt_file)
            file_result["warnings"].extend(parse_result.warnings)

            if not parse_result.payloads:
                raise ValueError("No executable evaluation request recognized in txt (must contain conditions + criteria)")

            for idx, payload in enumerate(parse_result.payloads, start=1):
                total_requests += 1

                if forced_granularity:
                    payload["forced_granularity"] = forced_granularity

                suffix_parts = []
                if run_tag:
                    suffix_parts.append(run_tag)
                if forced_granularity:
                    suffix_parts.append(forced_granularity)
                suffix = "__" + "__".join(suffix_parts) if suffix_parts else ""

                output_name = f"{txt_file.stem}__req{idx:02d}{suffix}__result.json"
                output_path = results_dir / output_name

                request_item = {
                    "request_index": idx,
                    "output_file": output_name,
                    "status": "ok",
                }

                try:
                    result = await run_single_request(payload)
                    output_path.write_text(
                        json.dumps(
                            {
                                "source_file": txt_file.name,
                                "request_index": idx,
                                "request": payload,
                                "result": result,
                            },
                            indent=2,
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
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
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    results_dir = Path(args.results_dir).resolve()

    if not dataset_dir.exists() or not dataset_dir.is_dir():
        print(f"[ERROR] dataset directory does not exist: {dataset_dir}")
        return 1

    return asyncio.run(
        run_batch(
            dataset_dir=dataset_dir,
            results_dir=results_dir,
            pattern=args.pattern,
            fail_fast=args.fail_fast,
            forced_granularity=args.forced_granularity,
            run_tag=args.run_tag,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
