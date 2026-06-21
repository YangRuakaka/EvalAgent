#!/usr/bin/env python3
"""
Rebuild dataset groups so each task group has exactly 2 JSON files.

If a task has an odd number of files, duplicate one file from the same task
to complete the final 2-file group.
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List


BACKUP_SUFFIX = "_original_backup"


def _parse_task_name(folder_name: str) -> str:
    if folder_name.endswith(BACKUP_SUFFIX):
        return folder_name[: -len(BACKUP_SUFFIX)]

    match = re.match(r"^(.*)_(\d+)$", folder_name)
    if match:
        return match.group(1)

    return folder_name


def _collect_task_dirs(base_dir: Path) -> Dict[str, List[Path]]:
    task_dirs: Dict[str, List[Path]] = {}
    for folder in sorted(d for d in base_dir.iterdir() if d.is_dir()):
        task_name = _parse_task_name(folder.name)
        task_dirs.setdefault(task_name, []).append(folder)
    return task_dirs


def _source_dirs_for_task(task_name: str, dirs: List[Path]) -> List[Path]:
    backup_dir = next((d for d in dirs if d.name == f"{task_name}{BACKUP_SUFFIX}"), None)
    if backup_dir is not None:
        return [backup_dir]

    plain_dirs = [d for d in dirs if d.name == task_name]
    if plain_dirs:
        return plain_dirs

    return sorted(dirs, key=lambda p: p.name)


def _load_task_files(source_dirs: List[Path]) -> Dict[str, bytes]:
    file_contents: Dict[str, bytes] = {}
    for source_dir in source_dirs:
        for json_file in sorted(source_dir.glob("*.json")):
            if json_file.name not in file_contents:
                file_contents[json_file.name] = json_file.read_bytes()
    return file_contents


def _build_pairs(file_names: List[str]) -> List[List[str]]:
    ordered = sorted(file_names)
    if len(ordered) % 2 == 1 and ordered:
        ordered.append(ordered[0])
    return [ordered[idx: idx + 2] for idx in range(0, len(ordered), 2)]


def _write_pair(group_dir: Path, pair: List[str], file_contents: Dict[str, bytes]) -> None:
    group_dir.mkdir(parents=True, exist_ok=True)
    written_names: Dict[str, int] = {}

    for file_name in pair:
        count = written_names.get(file_name, 0)
        written_names[file_name] = count + 1

        if count == 0:
            target_name = file_name
        else:
            source_path = Path(file_name)
            target_name = f"{source_path.stem}__dup{count}{source_path.suffix}"

        (group_dir / target_name).write_bytes(file_contents[file_name])


def split_group_folders(base_dir: Path) -> None:
    """
    Rebuild all task folders so every resulting group has exactly 2 JSON files.
    """

    task_dirs = _collect_task_dirs(base_dir)

    for task_name in sorted(task_dirs):
        related_dirs = task_dirs[task_name]
        source_dirs = _source_dirs_for_task(task_name, related_dirs)
        file_contents = _load_task_files(source_dirs)
        file_names = sorted(file_contents.keys())

        if not file_names:
            print(f"skip {task_name}: no json files")
            continue

        pairs = _build_pairs(file_names)
        print(f"task {task_name}: {len(file_names)} files -> {len(pairs)} groups")

        for old_dir in related_dirs:
            shutil.rmtree(old_dir)

        for idx, pair in enumerate(pairs, start=1):
            if len(pairs) == 1:
                group_name = task_name
            else:
                group_name = f"{task_name}_{idx}"

            group_dir = base_dir / group_name
            _write_pair(group_dir, pair, file_contents)
            print(f"  created {group_name}: {', '.join(pair)}")

    print("done: every group has exactly 2 files")


if __name__ == "__main__":
    DATA_DIR = Path("technical_evaluation/dataset/dataset_grouped_by_task")
    
    if not DATA_DIR.exists():
        print(f"Error: {DATA_DIR} not found")
        exit(1)
    
    split_group_folders(DATA_DIR)
