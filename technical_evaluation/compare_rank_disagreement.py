from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().lower()


def _canonical_condition_id(entry: Dict[str, Any]) -> Optional[str]:
    source_file = str(entry.get("source_file") or "").strip()
    if source_file:
        return Path(source_file).name.lower()

    condition_id = str(entry.get("condition_id") or "").strip()
    if condition_id:
        name = Path(condition_id).name.lower()
        return name.replace("__normalized", "")

    return None


def _extract_group_winner(group: Dict[str, Any]) -> Optional[str]:
    ranking = group.get("ranking")
    if not isinstance(ranking, list):
        return None

    rank1_entry: Optional[Dict[str, Any]] = None
    for item in ranking:
        if not isinstance(item, dict):
            continue
        rank_value = item.get("rank")
        try:
            rank_num = int(rank_value)
        except Exception:
            rank_num = None
        if rank_num == 1:
            rank1_entry = item
            break

    if rank1_entry is None and ranking:
        first = ranking[0]
        if isinstance(first, dict):
            rank1_entry = first

    if rank1_entry is None:
        return None
    return _canonical_condition_id(rank1_entry)


def _extract_group_rank_map(group: Dict[str, Any]) -> Dict[str, int]:
    rank_map: Dict[str, int] = {}
    ranking = group.get("ranking")
    if not isinstance(ranking, list):
        return rank_map

    for idx, item in enumerate(ranking, start=1):
        if not isinstance(item, dict):
            continue
        cid = _canonical_condition_id(item)
        if not cid:
            continue

        rank_value = item.get("rank")
        try:
            rank_num = int(rank_value)
        except Exception:
            rank_num = idx

        rank_map[cid] = rank_num

    return rank_map


def _parse_llm_ranking_file(path: Path) -> Dict[str, Any]:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON object in {path}")

    groups = data.get("groups")
    if not isinstance(groups, list):
        raise ValueError(f"Missing list field 'groups' in {path}")

    winners_by_group: Dict[str, str] = {}
    rank_maps_by_group: Dict[str, Dict[str, int]] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("group_id") or "").strip()
        if not group_id:
            continue
        winner = _extract_group_winner(group)
        if winner:
            winners_by_group[group_id] = winner
        rank_map = _extract_group_rank_map(group)
        if rank_map:
            rank_maps_by_group[group_id] = rank_map

    label_parts = [
        _normalize_token(data.get("judge_model")),
        _normalize_token(data.get("ranking_mode")),
        path.parent.name,
    ]
    label = " | ".join([p for p in label_parts if p])

    return {
        "path": str(path),
        "label": label or str(path),
        "judge_model": data.get("judge_model"),
        "ranking_mode": data.get("ranking_mode"),
        "group_count_total": data.get("group_count_total"),
        "group_count_evaluated": data.get("group_count_evaluated"),
        "winners_by_group": winners_by_group,
        "rank_maps_by_group": rank_maps_by_group,
    }


def _load_human_winners(path: Path) -> Dict[str, str]:
    data = _read_json(path)

    # Format A0: human_ranking_template style
    # {
    #   "groups": [
    #     {
    #       "group_id": "...",
    #       "items": [{"file_name": "...", "human_rank": 1}, ...],
    #       "ranking": ["...", "..."]
    #     }
    #   ]
    # }
    if isinstance(data, dict) and isinstance(data.get("groups"), list):
        winners_template: Dict[str, str] = {}
        for group in data["groups"]:
            if not isinstance(group, dict):
                continue
            gid = str(group.get("group_id") or "").strip()
            if not gid:
                continue

            winner: Optional[str] = None

            # Prefer explicit human_rank == 1 from items.
            items = group.get("items")
            if isinstance(items, list):
                best_rank = None
                best_name = None
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    file_name = str(item.get("file_name") or "").strip()
                    if not file_name:
                        continue
                    rank_val = item.get("human_rank")
                    try:
                        rank_num = int(rank_val)
                    except Exception:
                        rank_num = None
                    if rank_num is None:
                        continue
                    if best_rank is None or rank_num < best_rank:
                        best_rank = rank_num
                        best_name = file_name
                if best_name:
                    winner = Path(best_name).name.lower()

            # Fallback: first element from ranking string list.
            if winner is None:
                ranking = group.get("ranking")
                if isinstance(ranking, list) and ranking:
                    first = ranking[0]
                    if isinstance(first, str) and first.strip():
                        winner = Path(first.strip()).name.lower()

            if winner:
                winners_template[gid] = winner

        if winners_template:
            return winners_template

    # Format A: same schema as llm_group_ranking.json
    if isinstance(data, dict) and isinstance(data.get("groups"), list):
        winners: Dict[str, str] = {}
        for group in data["groups"]:
            if not isinstance(group, dict):
                continue
            gid = str(group.get("group_id") or "").strip()
            if not gid:
                continue
            winner = _extract_group_winner(group)
            if winner:
                winners[gid] = winner
        if winners:
            return winners

    # Format B: {"winners": {group_id: winner_id}}
    if isinstance(data, dict) and isinstance(data.get("winners"), dict):
        winners = {
            str(k): str(v).strip().lower()
            for k, v in data["winners"].items()
            if str(v).strip()
        }
        if winners:
            return winners

    # Format C: plain mapping {group_id: winner_id}
    if isinstance(data, dict):
        winners: Dict[str, str] = {}
        for k, v in data.items():
            if isinstance(v, str) and v.strip():
                winners[str(k)] = v.strip().lower()
        if winners:
            return winners

    # Format D: list of records [{group_id:..., winner:...}, ...]
    if isinstance(data, list):
        winners = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            gid = str(item.get("group_id") or "").strip()
            if not gid:
                continue
            winner_raw = (
                item.get("winner")
                or item.get("winner_id")
                or item.get("source_file")
                or item.get("condition_id")
            )
            if not winner_raw:
                continue
            winner_text = str(winner_raw).strip().lower()
            if winner_text:
                winners[gid] = Path(winner_text).name.lower()
        if winners:
            return winners

    raise ValueError(
        "Unsupported human file format. Supported formats: "
        "(1) llm_group_ranking style with groups/ranking, "
        "(2) {'winners': {group_id: winner}}, "
        "(3) plain {group_id: winner}, "
        "(4) list of records with group_id + winner fields."
    )


def _pairwise_disagreement(
    winners_a: Dict[str, str],
    winners_b: Dict[str, str],
) -> Dict[str, Any]:
    shared_groups = sorted(set(winners_a) & set(winners_b))
    if not shared_groups:
        return {
            "shared_group_count": 0,
            "agree_count": 0,
            "disagree_count": 0,
            "agreement_rate": None,
            "disagreement_rate": None,
            "disagreed_groups": [],
        }

    disagree_groups: List[str] = []
    agree_count = 0
    for gid in shared_groups:
        if winners_a[gid] == winners_b[gid]:
            agree_count += 1
        else:
            disagree_groups.append(gid)

    disagree_count = len(disagree_groups)
    total = len(shared_groups)
    return {
        "shared_group_count": total,
        "agree_count": agree_count,
        "disagree_count": disagree_count,
        "agreement_rate": agree_count / total,
        "disagreement_rate": disagree_count / total,
        "disagreed_groups": disagree_groups,
    }


def _group_level_spearman(
    rank_map_a: Dict[str, int],
    rank_map_b: Dict[str, int],
) -> Optional[float]:
    common_items = sorted(set(rank_map_a) & set(rank_map_b))
    n = len(common_items)
    if n < 2:
        return None

    d2_sum = 0.0
    for cid in common_items:
        diff = rank_map_a[cid] - rank_map_b[cid]
        d2_sum += float(diff * diff)

    denom = n * (n * n - 1)
    if denom == 0:
        return None
    return 1.0 - (6.0 * d2_sum / denom)


def _average_spearman_across_groups(
    rank_maps_a: Dict[str, Dict[str, int]],
    rank_maps_b: Dict[str, Dict[str, int]],
) -> Dict[str, Any]:
    shared_groups = sorted(set(rank_maps_a) & set(rank_maps_b))
    values: List[float] = []
    skipped_groups: List[str] = []

    for gid in shared_groups:
        corr = _group_level_spearman(rank_maps_a[gid], rank_maps_b[gid])
        if corr is None:
            skipped_groups.append(gid)
            continue
        values.append(corr)

    avg = (sum(values) / len(values)) if values else None
    return {
        "group_count_shared": len(shared_groups),
        "group_count_used": len(values),
        "group_count_skipped": len(skipped_groups),
        "average_spearman": avg,
        "skipped_groups": skipped_groups,
    }


def _accuracy_against_human(
    model_winners: Dict[str, str],
    human_winners: Dict[str, str],
) -> Dict[str, Any]:
    shared_groups = sorted(set(model_winners) & set(human_winners))
    if not shared_groups:
        return {
            "shared_group_count": 0,
            "correct_count": 0,
            "accuracy": None,
            "mismatch_groups": [],
        }

    correct = 0
    mismatches: List[Dict[str, str]] = []
    for gid in shared_groups:
        model_pick = model_winners[gid]
        human_pick = human_winners[gid]
        if model_pick == human_pick:
            correct += 1
        else:
            mismatches.append(
                {
                    "group_id": gid,
                    "model_winner": model_pick,
                    "human_winner": human_pick,
                }
            )

    total = len(shared_groups)
    return {
        "shared_group_count": total,
        "correct_count": correct,
        "accuracy": correct / total,
        "mismatch_groups": mismatches,
    }


def _format_rate(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _build_disagreement_cases(parsed_files: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    all_groups = sorted({gid for item in parsed_files for gid in item["winners_by_group"].keys()})
    cases: List[Dict[str, Any]] = []

    for gid in all_groups:
        winners = []
        present = []
        for idx, item in enumerate(parsed_files):
            winner = item["winners_by_group"].get(gid)
            rank_map = item["rank_maps_by_group"].get(gid, {})
            ranking_order = [
                {"condition_id": cid, "rank": rank}
                for cid, rank in sorted(rank_map.items(), key=lambda x: x[1])
            ]
            present.append(
                {
                    "file_index": idx,
                    "file_label": item["label"],
                    "winner": winner,
                    "ranking_order": ranking_order,
                }
            )
            if winner is not None:
                winners.append(winner)

        unique_winners = sorted(set(winners))
        if len(unique_winners) <= 1:
            continue

        cases.append(
            {
                "group_id": gid,
                "winner_set": unique_winners,
                "file_rank_views": present,
            }
        )

    return cases


def build_report(paths: Sequence[Path], human_file: Optional[Path]) -> Dict[str, Any]:
    parsed_files = [_parse_llm_ranking_file(path) for path in paths]
    pairwise_rows: List[Dict[str, Any]] = []

    for i, j in combinations(range(len(parsed_files)), 2):
        a = parsed_files[i]
        b = parsed_files[j]
        disagreement = _pairwise_disagreement(a["winners_by_group"], b["winners_by_group"])
        spearman = _average_spearman_across_groups(a["rank_maps_by_group"], b["rank_maps_by_group"])
        pairwise_rows.append(
            {
                "file_a_index": i,
                "file_b_index": j,
                "file_a_label": a["label"],
                "file_b_label": b["label"],
                "top1_disagreement": disagreement,
                "rank_correlation": spearman,
            }
        )

    human_metrics: List[Dict[str, Any]] = []
    human_payload: Optional[Dict[str, Any]] = None
    if human_file is not None:
        human_winners = _load_human_winners(human_file)
        human_payload = {
            "path": str(human_file),
            "winner_count": len(human_winners),
        }
        for idx, file_payload in enumerate(parsed_files):
            accuracy = _accuracy_against_human(file_payload["winners_by_group"], human_winners)
            human_metrics.append(
                {
                    "file_index": idx,
                    "file_label": file_payload["label"],
                    "metrics": accuracy,
                }
            )

    disagreement_cases = _build_disagreement_cases(parsed_files)

    return {
        "files": [
            {
                "index": i,
                "path": item["path"],
                "label": item["label"],
                "judge_model": item["judge_model"],
                "ranking_mode": item["ranking_mode"],
                "group_count_total": item["group_count_total"],
                "group_count_evaluated": item["group_count_evaluated"],
                "winner_count": len(item["winners_by_group"]),
            }
            for i, item in enumerate(parsed_files)
        ],
        "pairwise": pairwise_rows,
        "disagreement_cases": disagreement_cases,
        "human": human_payload,
        "accuracy_against_human": human_metrics,
    }


def print_summary(report: Dict[str, Any]) -> None:
    print("=== Input Files ===")
    for file_row in report.get("files", []):
        print(
            f"[{file_row['index']}] {file_row['label']} | "
            f"winners={file_row['winner_count']} | path={file_row['path']}"
        )

    print("\n=== Pairwise Top-1 Disagreement ===")
    for row in report.get("pairwise", []):
        disagreement = row["top1_disagreement"]
        corr = row["rank_correlation"]
        print(
            f"({row['file_a_index']} vs {row['file_b_index']}) "
            f"shared={disagreement['shared_group_count']}, "
            f"disagree={disagreement['disagree_count']}, "
            f"rate={_format_rate(disagreement['disagreement_rate'])}, "
            f"avg_spearman={_format_rate(corr['average_spearman'])}"
        )

    disagreement_cases = report.get("disagreement_cases") or []
    print(f"\n=== Disagreement Cases (unique top-1 winners > 1) ===\ncount={len(disagreement_cases)}")

    accuracy_rows = report.get("accuracy_against_human") or []
    if accuracy_rows:
        print("\n=== Accuracy Against Human ===")
        for row in accuracy_rows:
            metrics = row["metrics"]
            print(
                f"[{row['file_index']}] {row['file_label']} | "
                f"shared={metrics['shared_group_count']}, "
                f"correct={metrics['correct_count']}, "
                f"accuracy={_format_rate(metrics['accuracy'])}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare rank disagreement across multiple llm_group_ranking.json files, "
            "and optionally compute per-file accuracy against human winners."
        )
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Paths to llm_group_ranking.json files (>=2).",
    )
    parser.add_argument(
        "--human-file",
        type=str,
        default=None,
        help=(
            "Optional human winner file. Supported formats include llm_group_ranking style, "
            "{'winners': {...}}, or plain {group_id: winner}."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional output JSON path for the full report.",
    )
    parser.add_argument(
        "--disagreement-output",
        type=str,
        default=None,
        help=(
            "Optional output JSON path for disagreement-only cases. "
            "Each case includes per-file winner and ranking order."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = [Path(p).expanduser().resolve() for p in args.files]
    if len(paths) < 2:
        raise SystemExit("Need at least 2 ranking files to compare.")

    for path in paths:
        if not path.exists() or not path.is_file():
            raise SystemExit(f"File not found: {path}")

    human_file: Optional[Path] = None
    if args.human_file:
        human_file = Path(args.human_file).expanduser().resolve()
        if not human_file.exists() or not human_file.is_file():
            raise SystemExit(f"Human file not found: {human_file}")

    report = build_report(paths=paths, human_file=human_file)
    print_summary(report)

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nSaved report: {out_path}")

    if args.disagreement_output:
        out_path = Path(args.disagreement_output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "files": report.get("files", []),
            "disagreement_case_count": len(report.get("disagreement_cases", [])),
            "disagreement_cases": report.get("disagreement_cases", []),
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved disagreement cases: {out_path}")


if __name__ == "__main__":
    main()