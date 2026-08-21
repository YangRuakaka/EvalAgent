from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
from matplotlib.patches import Patch


# Default final-verdict accuracy values.
# You can override these by passing --verdict-json.
DEFAULT_FINAL_VERDICT_ACCURACY: Dict[str, float] = {
    "Baseline-GPT5": 0.759,
    "GPT5": 0.939,
    "Baseline-DeepSeek": 0.606,
    "DeepSeek": 0.788,
}

MODEL_ORDER = ["Baseline-GPT5", "GPT5", "Baseline-DeepSeek", "DeepSeek"]

MODEL_DISPLAY_NAME = {
    "Baseline-GPT5": "GPT-5 (Baseline)",
    "GPT5": "GPT-5 (Our Pipeline)",
    "Baseline-DeepSeek": "DeepSeek (Baseline)",
    "DeepSeek": "DeepSeek (Our Pipeline)",
}

COLORS = {
    "Baseline": "#b6c2cc",
    "GPT5": "#0b5fa5",
    "DeepSeek": "#1f8a4c",
    "Gain": "#1f1f1f",
    "Rank": "#4f7c95",
}


def _normalize_label_to_model_key(label: str) -> str:
    text = str(label or "").lower()
    is_baseline = "baseline" in text
    is_gpt5 = "gpt-5" in text
    is_deepseek = "deepseek" in text

    if is_baseline and is_gpt5:
        return "Baseline-GPT5"
    if is_baseline and is_deepseek:
        return "Baseline-DeepSeek"
    if is_gpt5:
        return "GPT5"
    if is_deepseek:
        return "DeepSeek"

    raise ValueError(f"Cannot infer model key from label: {label}")


def _load_rank_accuracy(rank_report: Path) -> Dict[str, float]:
    payload = json.loads(rank_report.read_text(encoding="utf-8"))
    rows = payload.get("accuracy_against_human")
    if not isinstance(rows, list):
        raise ValueError("rank report missing list field: accuracy_against_human")

    result: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("file_label") or "")
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        acc = metrics.get("accuracy")
        if acc is None:
            continue
        key = _normalize_label_to_model_key(label)
        result[key] = float(acc)

    for key in MODEL_ORDER:
        if key not in result:
            raise ValueError(f"rank accuracy missing model: {key}")

    return result


def _load_final_verdict_accuracy(verdict_json: Path | None) -> Dict[str, float]:
    if verdict_json is None:
        values = dict(DEFAULT_FINAL_VERDICT_ACCURACY)
    else:
        payload = json.loads(verdict_json.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("verdict json must be an object of {model: accuracy}")
        values = {str(k): float(v) for k, v in payload.items()}

    for key in MODEL_ORDER:
        if key not in values:
            raise ValueError(f"final verdict accuracy missing model: {key}")
        if not (0.0 <= values[key] <= 1.0):
            raise ValueError(f"final verdict accuracy out of range [0,1]: {key}={values[key]}")

    return values


def _set_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "font.size": 11,
            "font.family": "DejaVu Sans",
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            "axes.titleweight": "semibold",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def _print_metric_summary(final_verdict_accuracy: Dict[str, float], rank_accuracy: Dict[str, float], n_cases: int) -> None:
    print("[VERDICT/RANK] Input metrics")
    print(f"[VERDICT/RANK] N={n_cases}")

    for model in MODEL_ORDER:
        verdict = final_verdict_accuracy[model]
        rank = rank_accuracy[model]
        print(
            f"[VERDICT/RANK][MODEL] {MODEL_DISPLAY_NAME[model]}: "
            f"Final Verdict={verdict:.3f}, Rank={rank:.3f}"
        )

    gpt_verdict_gain = (final_verdict_accuracy["GPT5"] - final_verdict_accuracy["Baseline-GPT5"]) * 100
    ds_verdict_gain = (final_verdict_accuracy["DeepSeek"] - final_verdict_accuracy["Baseline-DeepSeek"]) * 100
    print(
        "[VERDICT/RANK][GAIN] Final Verdict: "
        f"GPT-5 +{gpt_verdict_gain:.1f}pp, DeepSeek +{ds_verdict_gain:.1f}pp"
    )

    rank_mean = float(np.mean([rank_accuracy[m] for m in MODEL_ORDER])) * 100
    rank_spread = (max(rank_accuracy.values()) - min(rank_accuracy.values())) * 100
    print(f"[VERDICT/RANK][DIST] Rank mean={rank_mean:.1f}%, spread={rank_spread:.1f}pp")


def _add_labels(ax: plt.Axes, bars: List[plt.Rectangle]) -> None:
    for bar in bars:
        h = bar.get_height()
        ax.annotate(
            f"{h * 100:.1f}%",
            xy=(bar.get_x() + bar.get_width() / 2.0, h),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )


def _plot_final_verdict_advantage(values: Dict[str, float], output_dir: Path) -> None:
    families = ["GPT-5", "DeepSeek"]
    x = np.arange(len(families), dtype=float)
    width = 0.34

    baseline_values = [values["Baseline-GPT5"], values["Baseline-DeepSeek"]]
    pipeline_values = [values["GPT5"], values["DeepSeek"]]
    gains = [p - b for b, p in zip(baseline_values, pipeline_values)]
    avg_gain = float(np.mean(gains))

    fig, ax = plt.subplots(figsize=(8.8, 5.2))

    bars_baseline = ax.bar(
        x - width / 2,
        baseline_values,
        width=width,
        color=[COLORS["Baseline"], "#cad5dd"],
        alpha=0.95,
        edgecolor="white",
        linewidth=0.9,
    )
    bars_pipeline = ax.bar(
        x + width / 2,
        pipeline_values,
        width=width,
        color=[COLORS["GPT5"], COLORS["DeepSeek"]],
        alpha=0.95,
        edgecolor="white",
        linewidth=0.9,
    )

    _add_labels(ax, list(bars_baseline))
    _add_labels(ax, list(bars_pipeline))

    for i, gain in enumerate(gains):
        ax.text(
            x[i],
            max(baseline_values[i], pipeline_values[i]) + 0.035,
            f"+{gain * 100:.1f}pp",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
            color=COLORS["Gain"],
        )

    ax.set_xticks(x)
    ax.set_xticklabels(families)
    ax.set_ylim(0.0, 1.08)
    ax.set_ylabel("Final Verdict Accuracy (%)")
    ax.set_title("Final Verdict Accuracy vs Baseline")
    ax.yaxis.set_major_locator(mtick.MultipleLocator(0.1))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1.0, decimals=0))
    ax.grid(axis="y", alpha=0.25)
    legend_handles = [
        Patch(facecolor=COLORS["Baseline"], edgecolor="white", label="GPT-5 (Baseline)"),
        Patch(facecolor=COLORS["GPT5"], edgecolor="white", label="GPT-5 (Our Pipeline)"),
        Patch(facecolor="#cad5dd", edgecolor="white", label="DeepSeek (Baseline)"),
        Patch(facecolor=COLORS["DeepSeek"], edgecolor="white", label="DeepSeek (Our Pipeline)"),
    ]
    ax.legend(handles=legend_handles, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=2)

    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(output_dir / "final_verdict_accuracy_vs_baseline.png")
    fig.savefig(output_dir / "final_verdict_accuracy_vs_baseline.pdf")
    plt.close(fig)


def _plot_rank_accuracy_distribution(rank_accuracy: Dict[str, float], output_dir: Path, n_cases_note: str | None) -> None:
    models = MODEL_ORDER
    x = np.arange(len(models), dtype=float)
    values = [rank_accuracy[m] for m in models]

    fig, ax = plt.subplots(figsize=(9.2, 5.2))

    bars = ax.bar(
        x,
        values,
        width=0.58,
        color=["#b6c2cc", COLORS["GPT5"], "#cad5dd", COLORS["DeepSeek"]],
        alpha=0.95,
        edgecolor="white",
        linewidth=0.9,
    )
    _add_labels(ax, list(bars))

    mean_val = float(np.mean(values))
    min_val = float(np.min(values))
    max_val = float(np.max(values))
    spread_pp = (max_val - min_val) * 100

    ax.axhline(mean_val, color=COLORS["Rank"], linewidth=1.6, linestyle="--", label=f"Mean: {mean_val * 100:.1f}%")
    ax.axhspan(min_val, max_val, color="#8db4c9", alpha=0.16, label=f"Range: {spread_pp:.1f}pp")

    title = "Rank Accuracy Distribution Across Four Methods"
    if n_cases_note:
        title = f"{title} ({n_cases_note})"

    ax.set_xticks(x)
    ax.set_xticklabels([MODEL_DISPLAY_NAME[m] for m in models], rotation=10)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Rank Accuracy (%)")
    ax.set_title(title)
    ax.yaxis.set_major_locator(mtick.MultipleLocator(0.1))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1.0, decimals=0))
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, loc="lower right")

    fig.tight_layout()
    fig.savefig(output_dir / "rank_accuracy_distribution.png")
    fig.savefig(output_dir / "rank_accuracy_distribution.pdf")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot Final Verdict and Rank metrics with a unified professional style."
    )
    parser.add_argument(
        "--rank-report",
        type=str,
        default="technical_evaluation/results/rank_disagreement_with_human_20260324.json",
        help="JSON report generated by compare_rank_disagreement.py with accuracy_against_human.",
    )
    parser.add_argument(
        "--verdict-json",
        type=str,
        default=None,
        help="Optional JSON for final verdict accuracy as {model: accuracy}.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="technical_evaluation/results/figures",
        help="Directory to save figure files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rank_report = Path(args.rank_report).expanduser().resolve()
    verdict_json = Path(args.verdict_json).expanduser().resolve() if args.verdict_json else None
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rank_payload = json.loads(rank_report.read_text(encoding="utf-8"))
    n_rank_cases = 0
    if isinstance(rank_payload, dict) and isinstance(rank_payload.get("human"), dict):
        n_rank_cases = int(rank_payload["human"].get("winner_count") or 0)

    final_verdict_accuracy = _load_final_verdict_accuracy(verdict_json)
    rank_accuracy = _load_rank_accuracy(rank_report)

    _set_style()
    _print_metric_summary(
        final_verdict_accuracy=final_verdict_accuracy,
        rank_accuracy=rank_accuracy,
        n_cases=n_rank_cases,
    )
    _plot_final_verdict_advantage(values=final_verdict_accuracy, output_dir=output_dir)
    _plot_rank_accuracy_distribution(
        rank_accuracy=rank_accuracy,
        output_dir=output_dir,
        n_cases_note=f"N={n_rank_cases}",
    )

    print(f"[DONE] Figures saved to: {output_dir}")
    print("[TYPE] Final verdict and rank figures")
    print("[FILES] final_verdict_accuracy_vs_baseline.(png|pdf)")
    print("[FILES] rank_accuracy_distribution.(png|pdf)")


if __name__ == "__main__":
    main()
