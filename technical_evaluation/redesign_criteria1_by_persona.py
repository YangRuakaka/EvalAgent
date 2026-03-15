from __future__ import annotations

import argparse
import itertools
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path


SATISFY = "satisfy"
NOT_SATISFY = "not_satisfy"
CONTROVERSIAL = "controversial"
DEFAULT_SATISFY_COUNT = 10
DEFAULT_NOT_SATISFY_COUNT = 10

OPPOSITE_DEFINITIONS = {
    "Conformity": (
        "acting on independent impulses, challenging prevailing expectations, "
        "and standing apart from social norms"
    ),
    "Convenience": (
        "accepting extra time, effort, and cognitive load instead of minimizing friction"
    ),
    "Frugality": (
        "luxury-oriented spending, choosing premium options, and prioritizing comfort or status over cost restraint"
    ),
    "Innovation": (
        "sticking to routine methods, relying on familiar solutions, and avoiding experimentation"
    ),
    "Sustainability": (
        "wasting energy and materials, choosing high-impact options, and prioritizing short-term convenience over long-term environmental outcomes"
    ),
    "Tradition": (
        "questioning inherited customs and prioritizing change or personal reinterpretation over established cultural, religious, and familial practices"
    ),
}

PERSONA_DEFINITION_OVERRIDES = {
    "Innovation": (
        "new or improved ideas, practical experimentation, and adopting better ways to solve problems"
    ),
}

VALUE_NAME_RE = re.compile(
    r"who values\s+(?P<name>.+?)\s+in\s+(?:their|her|his)\s+daily\s+life\.",
    re.IGNORECASE,
)
DEFINITION_RE = re.compile(
    r"The user defines\s+.+?\s+as\s+(?P<definition>.+?)(?:\.\s*)?$",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class DatasetEntry:
    file_path: Path
    data: dict
    persona_name: str
    persona_definition: str
    opposite_definition: str


@dataclass
class PlannedUpdate:
    entry: DatasetEntry
    bucket: str
    criteria1: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite criteria1 from persona definitions while distributing files into "
            "satisfy / not_satisfy / controversial buckets."
        )
    )
    parser.add_argument(
        "--dataset-dir",
        default="technical_evaluation/dataset",
        help="Directory containing top-level dataset JSON files.",
    )
    parser.add_argument(
        "--glob",
        default="*.json",
        help="Glob pattern for dataset files. Only top-level files are matched.",
    )
    parser.add_argument(
        "--satisfy-count",
        type=int,
        default=DEFAULT_SATISFY_COUNT,
        help="Number of files that should receive satisfy-oriented criteria.",
    )
    parser.add_argument(
        "--not-satisfy-count",
        type=int,
        default=DEFAULT_NOT_SATISFY_COUNT,
        help="Number of files that should receive not-satisfy-oriented criteria.",
    )
    parser.add_argument(
        "--preview-output",
        default="technical_evaluation/results/criteria1_persona_redesign_preview.json",
        help="Path to the preview report JSON.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply generated criteria1 text back to dataset files.",
    )
    return parser.parse_args()


def normalize_definition(raw_definition: str) -> str:
    definition = re.sub(r"\s+", " ", raw_definition).strip().rstrip(".")
    definition = re.sub(r"^The value placed on\s+", "", definition, flags=re.IGNORECASE)
    if definition:
        definition = definition[0].lower() + definition[1:]

    if re.search(r"\bvalue\b", definition, re.IGNORECASE):
        raise ValueError(f"Definition still contains forbidden wording: {raw_definition}")

    return definition


def extract_persona_info(persona_text: str) -> tuple[str, str]:
    if not persona_text or not isinstance(persona_text, str):
        raise ValueError("Missing persona text")

    normalized = persona_text.replace("\r\n", "\n").strip()
    name_match = VALUE_NAME_RE.search(normalized)
    definition_match = DEFINITION_RE.search(normalized.replace("\n", " "))

    if not name_match:
        raise ValueError(f"Unable to extract persona name from: {persona_text}")
    if not definition_match:
        raise ValueError(f"Unable to extract persona definition from: {persona_text}")

    persona_name = name_match.group("name").strip()
    persona_definition = normalize_definition(definition_match.group("definition"))
    persona_definition = PERSONA_DEFINITION_OVERRIDES.get(persona_name, persona_definition)
    return persona_name, persona_definition


def load_dataset_entries(dataset_dir: Path, glob_pattern: str) -> list[DatasetEntry]:
    files = sorted(path for path in dataset_dir.glob(glob_pattern) if path.is_file())
    entries: list[DatasetEntry] = []

    for file_path in files:
        with file_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict):
            raise ValueError(f"Dataset file is not a JSON object: {file_path}")

        persona_name, persona_definition = extract_persona_info(data.get("persona", ""))
        opposite_definition = OPPOSITE_DEFINITIONS.get(persona_name)
        if not opposite_definition:
            raise ValueError(f"Missing opposite definition for persona: {persona_name}")

        entries.append(
            DatasetEntry(
                file_path=file_path,
                data=data,
                persona_name=persona_name,
                persona_definition=persona_definition,
                opposite_definition=opposite_definition,
            )
        )

    return entries


def build_round_robin_order(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    grouped: dict[str, deque[DatasetEntry]] = defaultdict(deque)
    for entry in sorted(entries, key=lambda item: (item.persona_name.lower(), item.file_path.name.lower())):
        grouped[entry.persona_name].append(entry)

    ordered: list[DatasetEntry] = []
    persona_names = sorted(grouped)

    while True:
        progressed = False
        for persona_name in persona_names:
            bucket = grouped[persona_name]
            if bucket:
                ordered.append(bucket.popleft())
                progressed = True
        if not progressed:
            break

    return ordered


def assign_buckets(
    entries: list[DatasetEntry],
    satisfy_count: int,
    not_satisfy_count: int,
) -> list[tuple[DatasetEntry, str]]:
    total = len(entries)
    if total < satisfy_count + not_satisfy_count:
        raise ValueError(
            f"Dataset only has {total} files, which is fewer than satisfy_count + not_satisfy_count"
        )

    targets = {
        SATISFY: satisfy_count,
        NOT_SATISFY: not_satisfy_count,
        CONTROVERSIAL: total - satisfy_count - not_satisfy_count,
    }
    counts = {SATISFY: 0, NOT_SATISFY: 0, CONTROVERSIAL: 0}
    assigned: list[tuple[DatasetEntry, str]] = []
    cycle = itertools.cycle([SATISFY, NOT_SATISFY, CONTROVERSIAL])

    for entry in entries:
        for _ in range(3):
            candidate = next(cycle)
            if counts[candidate] < targets[candidate]:
                counts[candidate] += 1
                assigned.append((entry, candidate))
                break
        else:
            raise RuntimeError(f"Unable to assign bucket for {entry.file_path}")

    return assigned


def build_criteria_text(entry: DatasetEntry, bucket: str) -> str:
    if bucket == SATISFY:
        return (
            "Whether the agent's choices and reasoning reflect "
            f"{entry.persona_definition}."
        )
    if bucket == NOT_SATISFY:
        return (
            "Whether the agent's choices and reasoning reflect "
            f"{entry.opposite_definition}."
        )
    if bucket == CONTROVERSIAL:
        return (
            "Whether the agent's choices and reasoning alternate between "
            f"{entry.persona_definition} and {entry.opposite_definition}."
        )
    raise ValueError(f"Unknown bucket: {bucket}")


def plan_updates(
    entries: list[DatasetEntry], satisfy_count: int, not_satisfy_count: int
) -> list[PlannedUpdate]:
    ordered_entries = build_round_robin_order(entries)
    assigned = assign_buckets(ordered_entries, satisfy_count, not_satisfy_count)
    planned: list[PlannedUpdate] = []

    for entry, bucket in assigned:
        planned.append(
            PlannedUpdate(
                entry=entry,
                bucket=bucket,
                criteria1=build_criteria_text(entry, bucket),
            )
        )

    return planned


def write_preview(preview_path: Path, planned_updates: list[PlannedUpdate]) -> None:
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    totals = {SATISFY: 0, NOT_SATISFY: 0, CONTROVERSIAL: 0}

    items = []
    for planned in planned_updates:
        totals[planned.bucket] += 1
        items.append(
            {
                "file": planned.entry.file_path.as_posix(),
                "persona": planned.entry.persona_name,
                "bucket": planned.bucket,
                "criteria1": planned.criteria1,
            }
        )

    payload = {
        "summary": {
            "total": len(planned_updates),
            SATISFY: totals[SATISFY],
            NOT_SATISFY: totals[NOT_SATISFY],
            CONTROVERSIAL: totals[CONTROVERSIAL],
        },
        "items": items,
    }

    with preview_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def apply_updates(planned_updates: list[PlannedUpdate]) -> int:
    updated = 0

    for planned in planned_updates:
        data = dict(planned.entry.data)
        if data.get("criteria1") == planned.criteria1:
            continue

        data["criteria1"] = planned.criteria1
        with planned.entry.file_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        updated += 1

    return updated


def main() -> None:
    args = parse_args()
    dataset_dir = Path(args.dataset_dir)
    preview_path = Path(args.preview_output)

    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise SystemExit(f"Dataset directory not found: {dataset_dir}")
    if args.satisfy_count < 0 or args.not_satisfy_count < 0:
        raise SystemExit("Counts must be non-negative")

    entries = load_dataset_entries(dataset_dir, args.glob)
    if not entries:
        raise SystemExit("No dataset files matched.")

    planned_updates = plan_updates(entries, args.satisfy_count, args.not_satisfy_count)
    write_preview(preview_path, planned_updates)

    print(f"Scanned: {len(entries)} files")
    print(f"Preview written to: {preview_path.as_posix()}")

    if args.write:
        updated = apply_updates(planned_updates)
        print(f"Updated: {updated} files")
    else:
        print("No dataset files were modified. Re-run with --write to apply changes.")


if __name__ == "__main__":
    main()