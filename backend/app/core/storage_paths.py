"""Path helpers for separating cache history data and browser run outputs."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .config import Settings

_CACHE_DATASET_KEYS = ("data1", "data2", "data3")
_LEGACY_CACHE_DIR_NAMES = ("history_logs_cache", "history_logs")


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_backend_path(path_value: str | Path, root: Path | None = None) -> Path:
    base_root = root or backend_root()
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_root / candidate).resolve()


def normalize_cache_dataset(dataset: str) -> str:
    raw = str(dataset or "").strip().lower()
    mapping = {
        "1": "data1",
        "2": "data2",
        "3": "data3",
        "data1": "data1",
        "data2": "data2",
        "data3": "data3",
    }
    if raw in mapping:
        return mapping[raw]
    raise ValueError("Unsupported dataset. Use data1, data2, or data3.")


def get_cache_history_root(settings: Settings) -> Path:
    raw = str(getattr(settings, "CACHE_HISTORY_LOGS_DIR", "cache_history_logs") or "cache_history_logs").strip()
    return resolve_backend_path(raw)


def ensure_cache_dataset_dirs(settings: Settings) -> Dict[str, Path]:
    root = get_cache_history_root(settings)
    root.mkdir(parents=True, exist_ok=True)

    dataset_dirs: Dict[str, Path] = {}
    for dataset_key in _CACHE_DATASET_KEYS:
        dataset_dir = (root / dataset_key).resolve()
        dataset_dir.mkdir(parents=True, exist_ok=True)
        dataset_dirs[dataset_key] = dataset_dir
    return dataset_dirs


def get_cache_dataset_dir(settings: Settings, dataset: str) -> Path:
    dataset_key = normalize_cache_dataset(dataset)
    return ensure_cache_dataset_dirs(settings)[dataset_key]


def _get_explicit_legacy_browser_output_dir(settings: Settings) -> Path | None:
    legacy_raw = str(getattr(settings, "BROWSER_AGENT_OUTPUT_DIR", "") or "").strip()
    if not legacy_raw or legacy_raw == "history_logs":
        return None
    return resolve_backend_path(legacy_raw)


def get_browser_run_output_dir(settings: Settings) -> Path:
    new_raw = str(getattr(settings, "BROWSER_AGENT_RUN_OUTPUT_DIR", "") or "").strip()
    if new_raw:
        return resolve_backend_path(new_raw)

    explicit_legacy = _get_explicit_legacy_browser_output_dir(settings)
    if explicit_legacy is not None:
        return explicit_legacy

    return resolve_backend_path("browser_agent_runs")


def get_legacy_data1_dirs(settings: Settings) -> List[Path]:
    ordered: List[Path] = []
    explicit_legacy = _get_explicit_legacy_browser_output_dir(settings)
    if explicit_legacy is not None:
        ordered.append(explicit_legacy)

    root = backend_root()
    for dir_name in _LEGACY_CACHE_DIR_NAMES:
        candidate = (root / dir_name).resolve()
        if all(existing != candidate for existing in ordered):
            ordered.append(candidate)

    return ordered


def get_condition_lookup_dirs(settings: Settings) -> List[Path]:
    ordered: List[Path] = [get_browser_run_output_dir(settings)]
    ordered.extend(ensure_cache_dataset_dirs(settings).values())
    ordered.extend(get_legacy_data1_dirs(settings))

    deduped: List[Path] = []
    for candidate in ordered:
        if all(existing != candidate for existing in deduped):
            deduped.append(candidate)

    return deduped
