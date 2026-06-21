from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Mapping

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np


DEFAULT_VALUES: Dict[str, Dict[str, float]] = {
    "GPT5": {
        "Verdict Acc": 0.939,
        "Grounding Acc": 0.997,
        "Hit Rate": 0.649,
        "Overlap Rate": 0.911,
    },
    "DeepSeek": {
        "Verdict Acc": 0.788,
        "Grounding Acc": 0.997,
        "Hit Rate": 0.732,
        "Overlap Rate": 0.904,
    },
    "Baseline-GPT5": {
        "Verdict Acc": 0.759,
        "Grounding Acc": 0.774,
        "Hit Rate": 0.329,
        "Overlap Rate": 0.623,
    },
    "Baseline-DeepSeek": {
        "Verdict Acc": 0.606,
        "Grounding Acc": 0.675,
        "Hit Rate": 0.345,
        "Overlap Rate": 0.617,
    },
}

# Pair baseline with our pipeline to make model-family comparison direct.
MODEL_ORDER = ["Baseline-GPT5", "GPT5", "Baseline-DeepSeek", "DeepSeek"]
METRIC_ORDER = ["Grounding Acc", "Hit Rate", "Overlap Rate"]

COLORS = {
    "GPT5": "#0b5fa5",
    "DeepSeek": "#1f8a4c",
    "Baseline-GPT5": "#b6c2cc",
    "Baseline-DeepSeek": "#cad5dd",
}

MODEL_DISPLAY_NAME = {
    "GPT5": "GPT-5 (Our Pipeline)",
    "DeepSeek": "DeepSeek (Our Pipeline)",
    "Baseline-GPT5": "GPT-5 (Baseline)",
    "Baseline-DeepSeek": "DeepSeek (Baseline)",
}


def _validate_values(values: Mapping[str, Mapping[str, float]]) -> Dict[str, Dict[str, float]]:
    normalized: Dict[str, Dict[str, float]] = {}

    for model in MODEL_ORDER:
        if model not in values:
            raise ValueError(f"Missing model in data: {model}")
        model_metrics = values[model]
        normalized[model] = {}

        for metric in METRIC_ORDER:
            if metric not in model_metrics:
                raise ValueError(f"Missing metric '{metric}' for model '{model}'")
            value = float(model_metrics[metric])
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"Metric value out of range [0, 1]: model='{model}', metric='{metric}', value={value}"
                )
            normalized[model][metric] = value

    return normalized


def _load_values(input_json: Path | None) -> Dict[str, Dict[str, float]]:
    if input_json is None:
        return _validate_values(DEFAULT_VALUES)

    payload = json.loads(input_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object")

    return _validate_values(payload)


def _set_global_style() -> None:
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


def _format_percent_axis(ax: plt.Axes) -> None:
    ax.yaxis.set_major_locator(mtick.MultipleLocator(0.1))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1.0, decimals=0))


def _add_value_labels(ax: plt.Axes, bars: List[plt.Rectangle]) -> None:
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


def _print_metric_summary(values: Dict[str, Dict[str, float]], n_cases: int) -> None:
    print("[EVIDENCE] Evidence metric inputs")
    print(f"[EVIDENCE] N={n_cases}")

    for model in MODEL_ORDER:
        scores = ", ".join(f"{metric}={values[model][metric]:.3f}" for metric in METRIC_ORDER)
        print(f"[EVIDENCE][MODEL] {MODEL_DISPLAY_NAME[model]}: {scores}")

    print("[EVIDENCE][GAINS] Our Pipeline minus Baseline (percentage points)")
    for metric in METRIC_ORDER:
        gpt_gap = (values["GPT5"][metric] - values["Baseline-GPT5"][metric]) * 100
        ds_gap = (values["DeepSeek"][metric] - values["Baseline-DeepSeek"][metric]) * 100
        print(f"[EVIDENCE][GAIN] {metric}: GPT-5 +{gpt_gap:.1f}pp, DeepSeek +{ds_gap:.1f}pp")


def plot_grouped_bar(values: Dict[str, Dict[str, float]], output_dir: Path, n_cases: int) -> None:
    metrics = METRIC_ORDER
    models = MODEL_ORDER

    x = np.arange(len(metrics), dtype=float)
    width = 0.18

    fig, ax = plt.subplots(figsize=(9.5, 5.5))

    for i, model in enumerate(models):
        offsets = x + (i - (len(models) - 1) / 2.0) * width
        y = [values[model][m] for m in metrics]
        bars = ax.bar(
            offsets,
            y,
            width=width,
            label=MODEL_DISPLAY_NAME[model],
            color=COLORS[model],
            alpha=0.9,
            edgecolor="white",
            linewidth=0.8,
        )
        _add_value_labels(ax, list(bars))

    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    # Reserve extra headroom so gain annotations do not collide near the top.
    ax.set_ylim(0, 1.14)
    ax.set_ylabel("Score (%)")
    ax.set_title(f"Evidence Metrics Comparison (Grounding/Hit/Overlap)")
    ax.grid(axis="y", alpha=0.25)
    _format_percent_axis(ax)

    # Explicitly annotate model-baseline gains per metric for faster reading.
    for metric_idx, metric in enumerate(metrics):
        gpt_gap = values["GPT5"][metric] - values["Baseline-GPT5"][metric]
        ds_gap = values["DeepSeek"][metric] - values["Baseline-DeepSeek"][metric]
        ax.text(
            x[metric_idx],
            1.065,
            f"GPT-5 +{gpt_gap * 100:.1f}pp\nDeepSeek +{ds_gap * 100:.1f}pp",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#2f2f2f",
            bbox={"boxstyle": "round,pad=0.22", "facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
        )

    # Place legend outside the plotting area to avoid overlap with bars/labels.
    ax.legend(ncol=2, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.10))

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(output_dir / "technical_performance_grouped_bar.png")
    fig.savefig(output_dir / "technical_performance_grouped_bar.pdf")
    plt.close(fig)


def plot_metric_small_multiples(values: Dict[str, Dict[str, float]], output_dir: Path, n_cases: int) -> None:
    metrics = METRIC_ORDER
    models = MODEL_ORDER

    fig, axes = plt.subplots(1, len(metrics), figsize=(12, 4.8), sharey=True)
    if not isinstance(axes, np.ndarray):
        axes = np.array([axes])

    for idx, metric in enumerate(metrics):
        ax = axes[idx]
        y = [values[model][metric] for model in models]
        bars = ax.bar(
            [MODEL_DISPLAY_NAME[m] for m in models],
            y,
            color=[COLORS[m] for m in models],
            alpha=0.9,
            edgecolor="white",
            linewidth=0.8,
        )
        _add_value_labels(ax, list(bars))
        ax.set_title(metric)
        ax.set_ylim(0, 1.05)
        ax.grid(axis="y", alpha=0.25)
        _format_percent_axis(ax)
        ax.tick_params(axis="x", labelrotation=15)

        gpt_gap = values["GPT5"][metric] - values["Baseline-GPT5"][metric]
        ds_gap = values["DeepSeek"][metric] - values["Baseline-DeepSeek"][metric]
        ax.text(
            0.02,
            0.95,
            f"+{gpt_gap * 100:.1f}pp (GPT-5)\n+{ds_gap * 100:.1f}pp (DeepSeek)",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )

    fig.suptitle(f"Per-Metric Comparison by Model Family (N={n_cases})", y=1.03)
    fig.tight_layout()
    fig.savefig(output_dir / "technical_performance_small_multiples.png")
    fig.savefig(output_dir / "technical_performance_small_multiples.pdf")
    plt.close(fig)


def plot_gap_vs_baseline(values: Dict[str, Dict[str, float]], output_dir: Path, n_cases: int) -> None:
    metrics = METRIC_ORDER
    y = np.arange(len(metrics), dtype=float)
    height = 0.34

    gpt_gap = [values["GPT5"][m] - values["Baseline-GPT5"][m] for m in metrics]
    ds_gap = [values["DeepSeek"][m] - values["Baseline-DeepSeek"][m] for m in metrics]

    fig, ax = plt.subplots(figsize=(9.5, 5.5))

    bars_gpt = ax.barh(
        y + height / 2,
        gpt_gap,
        height=height,
        color=COLORS["GPT5"],
        alpha=0.9,
        label="GPT-5 vs Baseline",
    )
    bars_ds = ax.barh(
        y - height / 2,
        ds_gap,
        height=height,
        color=COLORS["DeepSeek"],
        alpha=0.9,
        label="DeepSeek vs Baseline",
    )

    for bars in (bars_gpt, bars_ds):
        for bar in bars:
            w = bar.get_width()
            y_center = bar.get_y() + bar.get_height() / 2
            ax.text(
                w + 0.005,
                y_center,
                f"+{w * 100:.1f}pp",
                va="center",
                ha="left",
                fontsize=9,
            )

    ax.axvline(0, color="#606060", linewidth=1.0)
    ax.set_yticks(y)
    ax.set_yticklabels(metrics)
    ax.set_xlabel("Absolute Improvement Over Baseline (percentage points)")
    ax.set_title(f"Model Advantage Over Baseline (N={n_cases})")
    ax.xaxis.set_major_locator(mtick.MultipleLocator(0.05))
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(xmax=1.0, decimals=0))
    ax.grid(axis="x", alpha=0.25)
    ax.legend(frameon=False, loc="lower right")

    fig.tight_layout()
    fig.savefig(output_dir / "technical_performance_gap_vs_baseline.png")
    fig.savefig(output_dir / "technical_performance_gap_vs_baseline.pdf")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot evidence metrics (Grounding Acc, Hit Rate, Overlap Rate) for baseline vs our pipeline."
    )
    parser.add_argument(
        "--input-json",
        type=str,
        default=None,
        help=(
            "Optional JSON file containing values in the form: "
            "{\"GPT5\": {\"Verdict Acc\": 0.939, ...}, ...}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="technical_evaluation/results/figures",
        help="Directory to save figures",
    )
    parser.add_argument(
        "--n-cases",
        type=int,
        default=33,
        help="Dataset size shown in figure titles",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_json = Path(args.input_json).resolve() if args.input_json else None
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    values = _load_values(input_json)
    _set_global_style()
    _print_metric_summary(values=values, n_cases=args.n_cases)

    plot_grouped_bar(values=values, output_dir=output_dir, n_cases=args.n_cases)
    plot_metric_small_multiples(values=values, output_dir=output_dir, n_cases=args.n_cases)
    plot_gap_vs_baseline(values=values, output_dir=output_dir, n_cases=args.n_cases)

    print(f"[DONE] Figures saved to: {output_dir}")
    print("[TYPE] Evidence metrics figures")
    print("[FILES] technical_performance_grouped_bar.(png|pdf)")
    print("[FILES] technical_performance_small_multiples.(png|pdf)")
    print("[FILES] technical_performance_gap_vs_baseline.(png|pdf)")


if __name__ == "__main__":
    main()
