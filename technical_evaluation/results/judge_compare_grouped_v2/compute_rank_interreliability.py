#!/usr/bin/env python3
"""Compute inter-reliability between human ranks and LLM ranks by task group.

Default behavior:
- Loads human ranks from judge_compare_grouped/human/human_eval.json
- Loads all llm_group_ranking.json under judge_compare_grouped/*/task_group_ranking_*/
- Excludes find_a_restaurant_to_have_dinner_with_friends by default

Metrics per group:
- Spearman rho (rank correlation)
- Kendall tau (pairwise concordance)
- Exact rank match ratio

Command examples:
- Use defaults/auto-discovery:
    python technical_evaluation/results/judge_compare_grouped_v2/compute_rank_interreliability.py
- Use explicit args:
    python technical_evaluation/results/judge_compare_grouped_v2/compute_rank_interreliability.py --human judge_compare_grouped/human/human_eval.json --llm-files judge_compare_grouped/gpt-4.1/task_group_ranking_xxx/llm_group_ranking.json
- Use manual paths configured at the top of this file:
    python technical_evaluation/results/judge_compare_grouped_v2/compute_rank_interreliability.py --use-manual-paths
"""

from __future__ import annotations

import argparse
from itertools import combinations
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


GroupRanks = Dict[str, Dict[str, int]]


# ---------------------------------------------------------------------------
# Manual path configuration (optional)
# 1) Edit the values below.
# 2) Run with: --use-manual-paths
# ---------------------------------------------------------------------------
MANUAL_HUMAN_FILE = Path("judge_compare_grouped/human/human_eval.json")
MANUAL_LLM_FILES: List[Path] = []
MANUAL_EXCLUDED_GROUPS = ["find_a_restaurant_to_have_dinner_with_friends"]


def parse_args() -> argparse.Namespace:
    default_excluded = ["find_a_restaurant_to_have_dinner_with_friends"]
    parser = argparse.ArgumentParser(description="Compute human-LLM rank inter-reliability.")
    parser.add_argument(
        "--use-manual-paths",
        action="store_true",
        help="Use MANUAL_* settings defined at the top of this file.",
    )
    parser.add_argument(
        "--human",
        type=Path,
        default=MANUAL_HUMAN_FILE,
        help="Path to human_eval.json",
    )
    parser.add_argument(
        "--llm-files",
        type=Path,
        nargs="*",
        default=None,
        help="Optional explicit llm_group_ranking.json file(s). If omitted, auto-discovers all.",
    )
    parser.add_argument(
        "--exclude-group",
        action="append",
        default=default_excluded,
        help="Group id to exclude. Can be used multiple times.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional output file path for machine-readable JSON results.",
    )
    parser.add_argument(
        "--pairwise-llm",
        action="store_true",
        help="Also compute pairwise inter-reliability between LLM models.",
    )
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="Print detailed rank differences between human and each model.",
    )
    parser.add_argument(
        "--show-all-items",
        action="store_true",
        help="When used with --show-diff, print all aligned items (not only mismatches).",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    # Use utf-8-sig so files with UTF-8 BOM can be parsed without errors.
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _coerce_rank(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        if v.lstrip("+-").isdigit():
            return int(v)
    return None


def load_human_ranks(human_file: Path, excluded_groups: Sequence[str]) -> GroupRanks:
    data = load_json(human_file)
    excluded = set(excluded_groups)
    result: GroupRanks = {}
    for group in data.get("groups", []):
        group_id = group.get("group")
        if not group_id or group_id in excluded:
            continue
        items = group.get("items", [])
        file_to_rank: Dict[str, int] = {}
        for item in items:
            source_file = item.get("file")
            if not source_file:
                continue
            rank = _coerce_rank(item.get("rank"))
            if rank is None:
                rank = _coerce_rank(item.get("note"))
            if rank is None:
                continue
            file_to_rank[source_file] = rank
        if file_to_rank:
            result[group_id] = file_to_rank
    return result


def load_llm_ranks(llm_file: Path, excluded_groups: Sequence[str]) -> GroupRanks:
    data = load_json(llm_file)
    excluded = set(excluded_groups)
    result: GroupRanks = {}
    for group in data.get("groups", []):
        group_id = group.get("group_id") or group.get("group")
        if not group_id or group_id in excluded:
            continue
        file_to_rank: Dict[str, int] = {}
        for item in group.get("ranking", []):
            source_file = item.get("source_file")
            rank = _coerce_rank(item.get("rank"))
            if not source_file or rank is None:
                continue
            file_to_rank[source_file] = rank
        if file_to_rank:
            result[group_id] = file_to_rank
    return result


def spearman_rho(human: Sequence[int], llm: Sequence[int]) -> float:
    n = len(human)
    if n < 2:
        return math.nan
    d2_sum = sum((a - b) ** 2 for a, b in zip(human, llm))
    return 1.0 - (6.0 * d2_sum) / (n * (n * n - 1))


def kendall_tau(human: Sequence[int], llm: Sequence[int]) -> float:
    n = len(human)
    if n < 2:
        return math.nan
    concordant = 0
    discordant = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            dh = human[i] - human[j]
            dl = llm[i] - llm[j]
            if dh == 0 or dl == 0:
                continue
            if (dh > 0 and dl > 0) or (dh < 0 and dl < 0):
                concordant += 1
            else:
                discordant += 1
    denom = concordant + discordant
    if denom == 0:
        return math.nan
    return (concordant - discordant) / denom


def safe_mean(values: Iterable[float]) -> float:
    finite = [v for v in values if not math.isnan(v)]
    if not finite:
        return math.nan
    return sum(finite) / len(finite)


def weighted_mean(values_and_weights: Iterable[Tuple[float, int]]) -> float:
    numerator = 0.0
    denominator = 0
    for value, weight in values_and_weights:
        if math.isnan(value):
            continue
        numerator += value * weight
        denominator += weight
    if denominator == 0:
        return math.nan
    return numerator / denominator


def evaluate_rank_maps(reference_ranks: GroupRanks, target_ranks: GroupRanks) -> dict:
    common_groups = sorted(set(reference_ranks) & set(target_ranks))

    per_group: List[dict] = []
    pooled_h: List[int] = []
    pooled_l: List[int] = []

    for group_id in common_groups:
        h_map = reference_ranks[group_id]
        l_map = target_ranks[group_id]
        common_files = sorted(set(h_map) & set(l_map))
        if len(common_files) < 2:
            continue

        h_vals = [h_map[f] for f in common_files]
        l_vals = [l_map[f] for f in common_files]

        rho = spearman_rho(h_vals, l_vals)
        tau = kendall_tau(h_vals, l_vals)
        exact = sum(1 for a, b in zip(h_vals, l_vals) if a == b) / len(common_files)

        per_group.append(
            {
                "group": group_id,
                "n_items": len(common_files),
                "spearman_rho": rho,
                "kendall_tau": tau,
                "exact_match": exact,
            }
        )
        pooled_h.extend(h_vals)
        pooled_l.extend(l_vals)

    overall = {
        "groups_evaluated": len(per_group),
        "items_pooled": len(pooled_h),
        "mean_spearman": safe_mean(g["spearman_rho"] for g in per_group),
        "weighted_mean_spearman": weighted_mean((g["spearman_rho"], g["n_items"]) for g in per_group),
        "mean_kendall": safe_mean(g["kendall_tau"] for g in per_group),
        "weighted_mean_kendall": weighted_mean((g["kendall_tau"], g["n_items"]) for g in per_group),
        "mean_exact_match": safe_mean(g["exact_match"] for g in per_group),
        "pooled_spearman": spearman_rho(pooled_h, pooled_l) if len(pooled_h) >= 2 else math.nan,
        "pooled_kendall": kendall_tau(pooled_h, pooled_l) if len(pooled_h) >= 2 else math.nan,
    }

    return {"overall": overall, "per_group": per_group}


def evaluate_one_model(human_ranks: GroupRanks, llm_ranks: GroupRanks) -> dict:
    return evaluate_rank_maps(human_ranks, llm_ranks)


def fmt(value: float) -> str:
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return f"{value:.4f}"


def discover_llm_files(root: Path) -> List[Path]:
    base = root / "judge_compare_grouped"
    return sorted(base.glob("*/task_group_ranking_*/llm_group_ranking.json"))


def print_report(model_name: str, result: dict) -> None:
    overall = result["overall"]
    print("=" * 88)
    print(f"Model: {model_name}")
    print(
        "Overall | groups={groups} items={items} "
        "mean_rho={mrho} weighted_rho={wrho} mean_tau={mtau} weighted_tau={wtau} "
        "mean_exact={mex} pooled_rho={prho} pooled_tau={ptau}".format(
            groups=overall["groups_evaluated"],
            items=overall["items_pooled"],
            mrho=fmt(overall["mean_spearman"]),
            wrho=fmt(overall["weighted_mean_spearman"]),
            mtau=fmt(overall["mean_kendall"]),
            wtau=fmt(overall["weighted_mean_kendall"]),
            mex=fmt(overall["mean_exact_match"]),
            prho=fmt(overall["pooled_spearman"]),
            ptau=fmt(overall["pooled_kendall"]),
        )
    )
    print("Per-group:")
    for g in result["per_group"]:
        print(
            "  - {group:<42} n={n_items:<2} rho={rho:<7} tau={tau:<7} exact={exact:<7}".format(
                group=g["group"],
                n_items=g["n_items"],
                rho=fmt(g["spearman_rho"]),
                tau=fmt(g["kendall_tau"]),
                exact=fmt(g["exact_match"]),
            )
        )


def print_rank_differences(
    reference_name: str,
    reference_ranks: GroupRanks,
    target_name: str,
    target_ranks: GroupRanks,
    show_all_items: bool,
) -> None:
    print("=" * 88)
    print(f"Detailed rank differences: {reference_name} vs {target_name}")

    common_groups = sorted(set(reference_ranks) & set(target_ranks))
    missing_groups_in_target = sorted(set(reference_ranks) - set(target_ranks))
    missing_groups_in_reference = sorted(set(target_ranks) - set(reference_ranks))

    if missing_groups_in_target:
        print(f"Groups only in {reference_name}: {', '.join(missing_groups_in_target)}")
    if missing_groups_in_reference:
        print(f"Groups only in {target_name}: {', '.join(missing_groups_in_reference)}")

    mismatch_count_total = 0
    aligned_count_total = 0

    for group_id in common_groups:
        h_map = reference_ranks[group_id]
        l_map = target_ranks[group_id]
        common_files = sorted(set(h_map) & set(l_map))
        if not common_files:
            continue

        rows: List[Tuple[str, int, int, int]] = []
        for source_file in common_files:
            h_rank = h_map[source_file]
            l_rank = l_map[source_file]
            delta = l_rank - h_rank
            rows.append((source_file, h_rank, l_rank, delta))

        aligned_count_total += len(rows)
        mismatch_count_total += sum(1 for _, h, l, _ in rows if h != l)

        display_rows = rows if show_all_items else [r for r in rows if r[1] != r[2]]
        if not display_rows:
            continue

        print(f"Group: {group_id} | aligned_items={len(rows)}")
        for source_file, h_rank, l_rank, delta in display_rows:
            sign = "+" if delta > 0 else ""
            tag = "MATCH" if delta == 0 else "DIFF"
            print(
                "  - {file} | human={h} model={m} delta={sign}{d} [{tag}]".format(
                    file=source_file,
                    h=h_rank,
                    m=l_rank,
                    sign=sign,
                    d=delta,
                    tag=tag,
                )
            )

    if aligned_count_total == 0:
        print("No aligned items between the two rank sets.")
        return

    print(
        "Summary | aligned_items={aligned} mismatches={mm} mismatch_rate={rate}".format(
            aligned=aligned_count_total,
            mm=mismatch_count_total,
            rate=fmt(mismatch_count_total / aligned_count_total),
        )
    )


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent

    excluded_groups = args.exclude_group
    selected_llm_files = args.llm_files
    human_file = args.human

    if args.use_manual_paths:
        human_file = MANUAL_HUMAN_FILE
        selected_llm_files = list(MANUAL_LLM_FILES)
        excluded_groups = list(MANUAL_EXCLUDED_GROUPS)

    if not human_file.is_absolute():
        human_file = script_dir.parent / human_file
    if not human_file.exists():
        raise FileNotFoundError(f"Human file not found: {human_file}")

    if selected_llm_files:
        llm_files = [p if p.is_absolute() else script_dir.parent / p for p in selected_llm_files]
    else:
        llm_files = discover_llm_files(script_dir.parent)

    llm_files = [p for p in llm_files if p.exists()]
    if not llm_files:
        raise FileNotFoundError("No llm_group_ranking.json files found.")

    human_ranks = load_human_ranks(human_file, excluded_groups)

    final_output = {
        "human_file": str(human_file),
        "excluded_groups": excluded_groups,
        "models": {},
    }

    llm_model_ranks: Dict[str, GroupRanks] = {}

    for llm_file in llm_files:
        llm_data = load_json(llm_file)
        model_name = llm_data.get("judge_model") or llm_file.parent.parent.name
        llm_ranks = load_llm_ranks(llm_file, excluded_groups)
        llm_model_ranks[model_name] = llm_ranks
        result = evaluate_one_model(human_ranks, llm_ranks)
        final_output["models"][model_name] = {
            "llm_file": str(llm_file),
            **result,
        }
        print_report(model_name, result)
        if args.show_diff:
            print_rank_differences(
                reference_name="human",
                reference_ranks=human_ranks,
                target_name=model_name,
                target_ranks=llm_ranks,
                show_all_items=args.show_all_items,
            )

    if args.pairwise_llm:
        final_output["pairwise_models"] = {}
        for model_a, model_b in combinations(sorted(llm_model_ranks.keys()), 2):
            result = evaluate_rank_maps(llm_model_ranks[model_a], llm_model_ranks[model_b])
            pair_id = f"{model_a}__vs__{model_b}"
            final_output["pairwise_models"][pair_id] = {
                "model_a": model_a,
                "model_b": model_b,
                **result,
            }
            print_report(f"{model_a} vs {model_b}", result)

    if args.output_json:
        output_path = args.output_json
        if not output_path.is_absolute():
            output_path = script_dir / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)
        print("=" * 88)
        print(f"Saved JSON report to: {output_path}")


if __name__ == "__main__":
    main()
