"""Shared data normalization helpers used across API modules."""
from __future__ import annotations

import json
import re
from typing import Any


def to_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def to_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [to_str(item) for item in value if item is not None]
    return [to_str(value)]


def normalize_to_string(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("value", "name", "label", "id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return ", ".join([normalize_to_string(v) for v in value if v is not None])
    return str(value)


def normalize_run_index(raw_run_index: Any, condition_id: str) -> int:
    if isinstance(raw_run_index, int):
        return raw_run_index

    if isinstance(raw_run_index, float):
        return int(raw_run_index)

    if isinstance(raw_run_index, str):
        digits = re.findall(r"\d+", raw_run_index)
        if digits:
            return int(digits[-1])

    match = re.search(r"run(\d+)", condition_id, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    return 1
