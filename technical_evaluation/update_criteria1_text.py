import argparse
import json
from pathlib import Path

TARGET_TEXT = "Whether the agent's behavior align with the core value defined by its assigned persona."


def update_criteria1_in_file(file_path: Path, target_text: str) -> bool:
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return False

    current = data.get("criteria1")
    if current == target_text:
        return False

    data["criteria1"] = target_text

    with file_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk update criteria1 for JSON files in dataset."
    )
    parser.add_argument(
        "--dataset-dir",
        default="technical_evaluation/dataset",
        help="Path to the dataset directory.",
    )
    parser.add_argument(
        "--glob",
        default="*.json",
        help="Glob pattern for files to update.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview how many files would change without writing.",
    )
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise SystemExit(f"Dataset directory not found: {dataset_dir}")

    files = sorted(dataset_dir.rglob(args.glob))
    if not files:
        print("No files matched.")
        return

    updated = 0
    total = 0
    errors = 0

    for file_path in files:
        total += 1
        try:
            if args.dry_run:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("criteria1") != TARGET_TEXT:
                    updated += 1
                continue

            if update_criteria1_in_file(file_path, TARGET_TEXT):
                updated += 1
        except Exception as exc:
            errors += 1
            print(f"[ERROR] {file_path}: {exc}")

    mode = "would be updated" if args.dry_run else "updated"
    print(f"Scanned: {total} files")
    print(f"{mode}: {updated} files")
    print(f"Errors: {errors} files")


if __name__ == "__main__":
    main()
