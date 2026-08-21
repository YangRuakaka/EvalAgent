import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TIMESTAMP_PREFIX = r"\[\d{2}:\d{2}:\d{2}\.\d{3}\]"

STEP_START_RE = re.compile(rf"^{TIMESTAMP_PREFIX}\s+STEP\s+(\d+)\/100\s+-\s+EXECUTION STARTED\s*$")
TAG_RE = re.compile(rf"^({TIMESTAMP_PREFIX})\s+([A-Z][A-Z\s\-]+?):\s*(.*)$")
STARTING_TASK_RE = re.compile(rf"^{TIMESTAMP_PREFIX}\s+🚀\s+Starting task:\s*$")
LAUNCH_RE = re.compile(rf"^({TIMESTAMP_PREFIX})\s+🎭\s+Launching new local browser playwright:(.*)$")
FINAL_RESULT_RE = re.compile(rf"^{TIMESTAMP_PREFIX}\s+FINAL RESULT:\s*(.*)$")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_starting_task_block(lines: List[str]) -> Tuple[str, str, str]:
    """
    Returns: (user_task, persona, full_starting_task_prompt)
    """
    start_idx = None
    for idx, line in enumerate(lines):
        if STARTING_TASK_RE.match(line):
            start_idx = idx
            break

    if start_idx is None:
        return "", "", ""

    block_lines: List[str] = []
    for line in lines[start_idx + 1 :]:
        if re.match(TIMESTAMP_PREFIX, line):
            break
        block_lines.append(line.rstrip("\n"))

    cleaned = [ln.strip() for ln in block_lines if ln.strip()]
    prompt = "\n".join(cleaned)

    intro_idx = None
    when_idx = None
    only_idx = None

    for idx, ln in enumerate(cleaned):
        if intro_idx is None and ln.startswith("You are an AI agent designed"):
            intro_idx = idx
        if when_idx is None and (
            ln.startswith("At each step explicitly report")
            or ln.startswith("When relevant explicitly report")
        ):
            when_idx = idx
        if only_idx is None and ln.startswith("Only refer to the mentioned value"):
            only_idx = idx

    persona_lines: List[str] = []
    if intro_idx is not None and when_idx is not None and when_idx > intro_idx:
        persona_lines = cleaned[intro_idx + 1 : when_idx]
    else:
        for ln in cleaned:
            if ln.startswith("Meet ") or ln.startswith("The user defines "):
                persona_lines.append(ln)

    if persona_lines and persona_lines[0].startswith("Meet "):
        persona_lines[0] = persona_lines[0][len("Meet ") :].strip()

    persona = "\n".join(persona_lines).strip()

    user_task = ""
    if only_idx is not None and only_idx + 1 < len(cleaned):
        trailing = [ln for ln in cleaned[only_idx + 1 :] if ln]
        user_task = "\n".join(trailing).strip()

    if not user_task:
        for ln in reversed(cleaned):
            if ln.startswith("You are an AI agent designed"):
                continue
            if ln.startswith("Meet "):
                continue
            if ln.startswith("The user defines "):
                continue
            if ln.startswith("At each step explicitly report"):
                continue
            if ln.startswith("When relevant explicitly report"):
                continue
            if ln.startswith("Only refer to the mentioned value"):
                continue
            user_task = ln
            break

    return user_task, persona, prompt


def extract_launch_line(lines: List[str]) -> str:
    for line in lines:
        m = LAUNCH_RE.match(line)
        if m:
            return line.strip()
    return ""


def extract_final_result(lines: List[str]) -> str:
    for i, line in enumerate(lines):
        m = FINAL_RESULT_RE.match(line)
        if not m:
            continue

        captured = [m.group(1).rstrip()]
        for ln in lines[i + 1 :]:
            if re.match(TIMESTAMP_PREFIX, ln):
                break
            captured.append(ln.rstrip("\n"))

        return "\n".join(captured).strip()
    return ""


def find_step_ranges(lines: List[str]) -> List[Tuple[int, int, int]]:
    """
    Returns list of (step_id, start_line_idx, end_line_idx_exclusive)
    """
    starts: List[Tuple[int, int]] = []
    for idx, line in enumerate(lines):
        m = STEP_START_RE.match(line)
        if m:
            starts.append((int(m.group(1)), idx))

    ranges: List[Tuple[int, int, int]] = []
    for i, (step_id, start_idx) in enumerate(starts):
        end_idx = starts[i + 1][1] if i + 1 < len(starts) else len(lines)
        ranges.append((step_id, start_idx, end_idx))
    return ranges


def _capture_multiline_after_tag(
    block_lines: List[str],
    start_index: int,
    first_line_rest: str,
    stop_tags: Optional[set] = None,
) -> str:
    stop_tags = stop_tags or {
        "EVALUATION",
        "MEMORY",
        "TARGET OBJECTIVE",
        "ACTION DECISION",
        "MULTI-ACTION SEQUENCE",
        "STEP",
    }

    captured: List[str] = [first_line_rest.rstrip()] if first_line_rest else []

    for ln in block_lines[start_index + 1 :]:
        stripped = ln.rstrip("\n")
        tag_match = TAG_RE.match(stripped)
        if tag_match:
            tag_name = tag_match.group(2).strip()
            if tag_name in stop_tags:
                break
        if STEP_START_RE.match(stripped):
            break
        if stripped.startswith("================================================================================"):
            break
        captured.append(stripped)

    joined = "\n".join(captured).strip()
    return joined


def extract_field_from_step(block_lines: List[str], tag: str) -> str:
    for i, line in enumerate(block_lines):
        m = TAG_RE.match(line)
        if not m:
            continue
        if m.group(2).strip() == tag:
            return _capture_multiline_after_tag(block_lines, i, m.group(3))
    return ""


def extract_reasoning(block_lines: List[str]) -> str:
    reasoning = extract_field_from_step(block_lines, "AI REASONING")
    if not reasoning:
        return ""

    if "<think>" in reasoning and "</think>" in reasoning:
        inner = reasoning.split("<think>", 1)[1].split("</think>", 1)[0]
        return inner.strip()

    return reasoning.strip()


def extract_action_tag_content(block_lines: List[str], tag: str) -> str:
    for i, line in enumerate(block_lines):
        m = TAG_RE.match(line)
        if not m:
            continue
        if m.group(2).strip() != tag:
            continue

        first = m.group(3).rstrip()
        extra: List[str] = []
        for ln in block_lines[i + 1 :]:
            if re.match(TIMESTAMP_PREFIX, ln):
                break
            if STEP_START_RE.match(ln):
                break
            if ln.startswith("================================================================================"):
                break
            extra.append(ln.rstrip("\n"))

        if extra:
            return (first + "\n" + "\n".join(extra)).strip()
        return first.strip()

    return ""


def extract_fallback_line(prefix: str, block_text: str) -> str:
    m = re.search(rf"^{re.escape(prefix)}\s*(.+)$", block_text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_step(block_lines: List[str], step_id: int) -> Dict[str, str]:
    block_text = "\n".join(block_lines)

    evaluation = extract_field_from_step(block_lines, "EVALUATION")
    if not evaluation:
        evaluation = extract_fallback_line("Evaluation of Previous Goal:", block_text)

    memory = extract_field_from_step(block_lines, "MEMORY")
    if not memory:
        memory = extract_fallback_line("Memory:", block_text)

    target_objective = extract_field_from_step(block_lines, "TARGET OBJECTIVE")
    if not target_objective:
        target_objective = extract_fallback_line("Next Goal:", block_text)

    reasoning = extract_reasoning(block_lines)

    multi_action = extract_action_tag_content(block_lines, "MULTI-ACTION SEQUENCE")
    action_decision = extract_action_tag_content(block_lines, "ACTION DECISION")

    if multi_action and action_decision:
        action = f"{multi_action}\n{action_decision}"
    elif multi_action:
        action = multi_action
    elif action_decision:
        action = action_decision
    else:
        action = ""

    return {
        "step_id": step_id,
        "EVALUATION": evaluation,
        "MEMORY": memory,
        "TARGET OBJECTIVE": target_objective,
        "AI REASONING": reasoning,
        "ACTION": action,
    }


def replace_done_text_with_final_result(action: str, final_result: str) -> str:
    if not action or not final_result or "done(text=" not in action:
        return action

    escaped = (
        final_result.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )

    pattern_with_success = re.compile(r'done\(text=".*?",\s*success=', flags=re.DOTALL)
    if pattern_with_success.search(action):
        return pattern_with_success.sub(f'done(text="{escaped}", success=', action)

    pattern_text_only = re.compile(r'done\(text=".*?"\)', flags=re.DOTALL)
    if pattern_text_only.search(action):
        return pattern_text_only.sub(f'done(text="{escaped}")', action)

    return action


def parse_log_file(path: Path, data_id: str) -> Dict:
    text = read_text(path)
    lines = text.splitlines()

    user_task, persona, prompt = extract_starting_task_block(lines)
    launch = extract_launch_line(lines)
    final_result = extract_final_result(lines)

    task = user_task.strip()

    steps: List[Dict] = []
    for sid, start_idx, end_idx in find_step_ranges(lines):
        block_lines = lines[start_idx:end_idx]
        steps.append(extract_step(block_lines, sid))

    if steps and final_result:
        last_action = steps[-1].get("ACTION", "")
        steps[-1]["ACTION"] = replace_done_text_with_final_result(last_action, final_result)

    return {
        "data_id": data_id,
        "source_file": path.name,
        "task": task,
        "launch": launch,
        "persona": persona,
        "starting_task_prompt": prompt,
        "steps": steps,
    }


def is_done_action(action: str) -> bool:
    return bool(action) and action.strip().startswith("done(")


def convert_dataset(
    dataset_dir: Path,
    output_dir: Path,
    non_done_dir: Path,
    overwrite: bool,
) -> Tuple[int, int, int]:
    txt_files = sorted([p for p in dataset_dir.rglob("*.txt") if p.is_file()])

    converted = 0
    skipped = 0
    moved_non_done = 0

    for index, txt_path in enumerate(txt_files, start=1):
        data_id = f"data_{index:06d}"
        parsed = parse_log_file(txt_path, data_id)

        last_action = ""
        if parsed.get("steps"):
            last_action = parsed["steps"][-1].get("ACTION", "")

        use_non_done_dir = not is_done_action(last_action)
        out_path = (non_done_dir if use_non_done_dir else output_dir) / f"{txt_path.stem}.json"
        counterpart_path = (output_dir if use_non_done_dir else non_done_dir) / f"{txt_path.stem}.json"

        if out_path.exists() and not overwrite:
            skipped += 1
            continue

        if overwrite and counterpart_path.exists():
            counterpart_path.unlink()

        out_path.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        converted += 1
        if use_non_done_dir:
            moved_non_done += 1

    return converted, skipped, moved_non_done


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert browser-use txt logs into structured JSON files.")
    parser.add_argument(
        "--dataset-dir",
        type=str,
        default="technical_evaluation/dataset",
        help="Path to dataset directory containing .txt files",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .json files",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for generated .json files (defaults to --dataset-dir)",
    )
    parser.add_argument(
        "--non-done-dir",
        type=str,
        default=None,
        help="Directory for files whose last step ACTION is not done(...) (defaults to <output-dir>/non_done)",
    )
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")

    output_dir = Path(args.output_dir) if args.output_dir else dataset_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    non_done_dir = Path(args.non_done_dir) if args.non_done_dir else (output_dir / "non_done")
    non_done_dir.mkdir(parents=True, exist_ok=True)

    converted, skipped, moved_non_done = convert_dataset(
        dataset_dir,
        output_dir,
        non_done_dir,
        args.overwrite,
    )
    print(
        f"Done. Converted {converted} files, skipped {skipped} files. "
        f"Moved {moved_non_done} non-done files to: {non_done_dir}"
    )


if __name__ == "__main__":
    main()
