from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import numpy as np
import pandas as pd

try:
	from scipy.stats import wilcoxon
except Exception:  # pragma: no cover - scipy might be unavailable
	wilcoxon = None

import matplotlib.pyplot as plt


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
OUTPUT_DIR = BASE_DIR / "output"


DAG_PATH = RESULTS_DIR / "User study record - DAG.csv"
EVIDENCE_PATH = RESULTS_DIR / "User study record - Evidence.csv"
PROFILE_PATH = RESULTS_DIR / "User study record - User Profile.csv"


METRIC_RENAME = {
	"Q2_1": "mental_demand",
	"Q3_1": "physical_demand",
	"Q5_1": "temporal_demand",
	"Q6_1": "frustration",
	"Q7_1": "effort",
	"Q8_1": "performance",
	"Q9_1": "confidence",
	"Q10_1": "evidence_findability",
	"Q11_1": "step_pinpointing",
}


DAG_EXTRA_RENAME = {
	"Q12_1": "actionable_recommendations",
	"Q13_1": "divergence_understanding",
	"Q14_1": "comparison_efficiency",
}


EVIDENCE_EXTRA_RENAME = {
	"Q15_1": "less_manual_log_search",
	"Q16_1": "reasoning_panel_helpful",
}


LOWER_BETTER_METRICS = {
	"mental_demand",
	"physical_demand",
	"temporal_demand",
	"frustration",
	"effort",
	"nasa_workload_5d",
}


CONDITION_A = "Condition A"
CONDITION_B = "Condition B"
CONDITION_C = "Condition C"


CORE_SHARED_METRICS = [
	"mental_demand",
	"physical_demand",
	"temporal_demand",
	"frustration",
	"effort",
	"performance",
	"confidence",
	"evidence_findability",
	"step_pinpointing",
	"nasa_workload_5d",
]


AB_UNIQUE_METRICS = [
	"actionable_recommendations",
	"divergence_understanding",
	"comparison_efficiency",
]


AC_UNIQUE_METRICS = [
	"less_manual_log_search",
	"reasoning_panel_helpful",
]


NASA_MAIN_METRICS = [
	"nasa_workload_5d",
	"mental_demand",
	"physical_demand",
	"temporal_demand",
	"effort",
	"frustration",
	"performance",
]

NASA_METRIC_SET = set(NASA_MAIN_METRICS)


def safe_to_numeric(series: pd.Series) -> pd.Series:
	return pd.to_numeric(series, errors="coerce")


def cohen_dz(diff: pd.Series) -> float:
	valid = diff.dropna()
	if len(valid) < 2:
		return np.nan
	std = valid.std(ddof=1)
	if std == 0 or np.isnan(std):
		return np.nan
	return valid.mean() / std


def wilcoxon_pvalue(diff: pd.Series, alternative: str = "two-sided") -> float:
	valid = diff.dropna()
	if wilcoxon is None or len(valid) < 3:
		return np.nan
	if np.allclose(valid.values, 0):
		return 1.0
	try:
		return float(wilcoxon(valid.values, alternative=alternative, zero_method="wilcox").pvalue)
	except TypeError:
		# Older scipy versions may not support `alternative`.
		return float(wilcoxon(valid.values, zero_method="wilcox").pvalue)
	except ValueError:
		return np.nan


def clean_rows(df: pd.DataFrame, user_col: str, cond_col: str) -> pd.DataFrame:
	out = df.copy()
	out = out.dropna(subset=[user_col, cond_col])

	# Remove Qualtrics metadata rows like {"ImportId":"..."}.
	mask_meta = out[user_col].astype(str).str.contains("ImportId", na=False)
	out = out[~mask_meta]

	# Keep only numeric user IDs.
	out[user_col] = safe_to_numeric(out[user_col])
	out = out[out[user_col].notna()]
	out[user_col] = out[user_col].astype(int)
	return out


def load_survey(path: Path, source_name: str) -> pd.DataFrame:
	raw = pd.read_csv(path)
	user_col = "Q15" if source_name == "dag" else "Q17"
	cond_col = "Q1"

	df = clean_rows(raw, user_col=user_col, cond_col=cond_col)
	rename_map = {**METRIC_RENAME}
	if source_name == "dag":
		rename_map.update(DAG_EXTRA_RENAME)
	if source_name == "evidence":
		rename_map.update(EVIDENCE_EXTRA_RENAME)

	keep_cols = [user_col, cond_col, *rename_map.keys()]
	df = df[keep_cols].rename(columns={user_col: "user_id", cond_col: "condition", **rename_map})

	numeric_cols = [c for c in df.columns if c not in {"user_id", "condition"}]
	for c in numeric_cols:
		df[c] = safe_to_numeric(df[c])

	# Preserve original row order to infer first/second usage for each user.
	df = df.reset_index(drop=True)
	df["usage_order"] = df.groupby("user_id").cumcount() + 1
	df["source"] = source_name

	df["is_condition_a"] = df["condition"].eq("Condition A")
	df["reduced_condition"] = np.where(df["is_condition_a"], np.nan, df["condition"])

	# Keep one aggregate NASA metric (legacy column name kept for compatibility).
	# All survey items are on a 1-10 scale, so reversed performance is 11 - performance.
	df["performance_rev"] = 11 - df["performance"]
	df["nasa_workload_5d"] = df[
		[
			"mental_demand",
			"physical_demand",
			"temporal_demand",
			"frustration",
			"effort",
			"performance_rev",
		]
	].mean(axis=1)

	return df


def load_profile() -> pd.DataFrame:
	# This file has two metadata rows before actual responses.
	raw = pd.read_csv(PROFILE_PATH, header=None)
	header_idx = None
	for i in range(len(raw)):
		row_values = raw.iloc[i].astype(str).tolist()
		if "Q9" in row_values:
			header_idx = i
			break
	if header_idx is None:
		raise ValueError(f"Could not locate profile header row in {PROFILE_PATH}")

	headers = raw.iloc[header_idx].tolist()
	data = raw.iloc[header_idx + 2 :].copy()
	data.columns = headers

	data = data.dropna(subset=["Q9"])
	data = data[~data["Q9"].astype(str).str.contains("ImportId", na=False)]

	out = data[["Q9", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]].copy()
	out = out.rename(
		columns={
			"Q9": "user_id",
			"Q2": "role",
			"Q3": "years_experience",
			"Q4": "llm_knowledge",
			"Q5": "agent_experience",
			"Q6": "debug_audit_frequency",
			"Q7": "agent_concepts",
		}
	)
	out["user_id"] = safe_to_numeric(out["user_id"]).astype("Int64")
	out = out[out["user_id"].notna()].copy()
	out["user_id"] = out["user_id"].astype(int)
	return out


def get_metric_columns(df: pd.DataFrame) -> List[str]:
	excluded = {
		"user_id",
		"condition",
		"usage_order",
		"source",
		"is_condition_a",
		"reduced_condition",
		"performance_rev",
		"role",
		"years_experience",
		"llm_knowledge",
		"agent_experience",
		"debug_audit_frequency",
		"agent_concepts",
	}
	metrics = []
	for c in df.columns:
		if c in excluded:
			continue
		if pd.api.types.is_numeric_dtype(df[c]):
			metrics.append(c)
	return metrics


def build_pairs_by_condition(df: pd.DataFrame) -> pd.DataFrame:
	rows = []
	for (source, user_id), grp in df.groupby(["source", "user_id"], sort=False):
		if grp["condition"].nunique() < 2:
			continue

		row_a = grp[grp["condition"] == "Condition A"]
		row_r = grp[grp["condition"] != "Condition A"]
		if row_a.empty or row_r.empty:
			continue

		row_a = row_a.iloc[0]
		row_r = row_r.iloc[0]

		out = {
			"source": source,
			"user_id": user_id,
			"reduced_condition": row_r["condition"],
			"condition_order": "A_first" if row_a["usage_order"] < row_r["usage_order"] else "A_second",
		}

		for c in get_metric_columns(df):
			out[f"{c}_a"] = row_a.get(c, np.nan)
			out[f"{c}_reduced"] = row_r.get(c, np.nan)
			out[f"{c}_diff_a_minus_reduced"] = row_a.get(c, np.nan) - row_r.get(c, np.nan)

		rows.append(out)

	return pd.DataFrame(rows)


def summarize_condition_effect(pairs: pd.DataFrame, metrics: Iterable[str], scope: str) -> pd.DataFrame:
	rows = []
	for m in metrics:
		col_a = f"{m}_a"
		col_r = f"{m}_reduced"
		col_d = f"{m}_diff_a_minus_reduced"
		if col_d not in pairs.columns:
			continue

		diff = pairs[col_d]
		rows.append(
			{
				"scope": scope,
				"metric": m,
				"n_pairs": int(diff.notna().sum()),
				"mean_A": float(pairs[col_a].mean()),
				"mean_reduced": float(pairs[col_r].mean()),
				"mean_diff_A_minus_reduced": float(diff.mean()),
				"cohen_dz": float(cohen_dz(diff)),
				"wilcoxon_p_two_sided": float(wilcoxon_pvalue(diff, alternative="two-sided")),
			}
		)

	out = pd.DataFrame(rows)
	if not out.empty:
		out = out.sort_values(["scope", "metric"]).reset_index(drop=True)
	return out


def select_shared_metrics_between_ab_and_ac(pairs: pd.DataFrame, metrics: Iterable[str]) -> List[str]:
	shared = []
	pairs_b = pairs[pairs["reduced_condition"] == CONDITION_B]
	pairs_c = pairs[pairs["reduced_condition"] == CONDITION_C]
	for m in metrics:
		col_d = f"{m}_diff_a_minus_reduced"
		if col_d not in pairs.columns:
			continue
		n_b = int(pairs_b[col_d].notna().sum()) if col_d in pairs_b.columns else 0
		n_c = int(pairs_c[col_d].notna().sum()) if col_d in pairs_c.columns else 0
		if n_b > 0 and n_c > 0:
			shared.append(m)
	return shared


def select_non_nasa_metrics_for_pairs(
	pairs: pd.DataFrame,
	metrics: Iterable[str],
	excluded_metrics: Iterable[str] | None = None,
) -> List[str]:
	excluded = set(excluded_metrics or [])
	selected = []
	for m in metrics:
		if m in NASA_METRIC_SET:
			continue
		if m in excluded:
			continue
		dcol = f"{m}_diff_a_minus_reduced"
		if dcol not in pairs.columns:
			continue
		if int(pairs[dcol].notna().sum()) > 0:
			selected.append(m)
	return selected


def build_first_second_pairs(df: pd.DataFrame) -> pd.DataFrame:
	rows = []
	for (source, user_id), grp in df.groupby(["source", "user_id"], sort=False):
		if set(grp["usage_order"].dropna().astype(int).tolist()) != {1, 2}:
			continue
		first = grp[grp["usage_order"] == 1].iloc[0]
		second = grp[grp["usage_order"] == 2].iloc[0]
		out = {
			"source": source,
			"user_id": user_id,
			"condition_first": first["condition"],
			"condition_second": second["condition"],
		}
		for c in get_metric_columns(df):
			out[f"{c}_first"] = first.get(c, np.nan)
			out[f"{c}_second"] = second.get(c, np.nan)
			out[f"{c}_diff_second_minus_first"] = second.get(c, np.nan) - first.get(c, np.nan)
		rows.append(out)
	return pd.DataFrame(rows)


def summarize_learning_effect(first_second: pd.DataFrame, metrics: Iterable[str]) -> pd.DataFrame:
	rows = []
	for m in metrics:
		dcol = f"{m}_diff_second_minus_first"
		if dcol not in first_second.columns:
			continue
		diff_raw = first_second[dcol]

		# Normalize so positive = better UX.
		if m in LOWER_BETTER_METRICS:
			diff_better = -diff_raw
		else:
			diff_better = diff_raw

		improved = (diff_better > 0).sum()
		worsened = (diff_better < 0).sum()
		same = (diff_better == 0).sum()

		rows.append(
			{
				"metric": m,
				"n_pairs": int(diff_raw.notna().sum()),
				"mean_first": float(first_second[f"{m}_first"].mean()),
				"mean_second": float(first_second[f"{m}_second"].mean()),
				"mean_diff_second_minus_first": float(diff_raw.mean()),
				"mean_diff_better_direction": float(diff_better.mean()),
				"improved_count": int(improved),
				"worsened_count": int(worsened),
				"same_count": int(same),
				"cohen_dz_better_direction": float(cohen_dz(diff_better)),
				"wilcoxon_p_two_sided": float(wilcoxon_pvalue(diff_better, alternative="two-sided")),
				"wilcoxon_p_second_better_one_sided": float(
					wilcoxon_pvalue(diff_better, alternative="greater")
				),
			}
		)
	out = pd.DataFrame(rows)
	if not out.empty:
		out = out.sort_values("metric").reset_index(drop=True)
	return out


def plot_core_metrics_by_condition(df: pd.DataFrame, output_file: Path) -> None:
	condition_order = [CONDITION_A, CONDITION_B, CONDITION_C]
	available = [m for m in NASA_MAIN_METRICS if m in df.columns]
	if not available:
		return

	n = len(available)
	fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 4.2), constrained_layout=True)
	if n == 1:
		axes = [axes]

	for ax, m in zip(axes, available):
		series_by_condition = [
			df[df["condition"] == cond][m].dropna().values for cond in condition_order
		]
		if all(len(s) == 0 for s in series_by_condition):
			ax.axis("off")
			continue
		ax.boxplot(series_by_condition, tick_labels=["A", "B", "C"], widths=0.55)
		ax.set_title(m)
		ax.grid(axis="y", alpha=0.25)

	fig.suptitle("NASA Metrics by Condition (A vs B vs C)")
	fig.savefig(output_file, dpi=180)
	plt.close(fig)


def plot_paired_metrics(
	pairs: pd.DataFrame,
	metrics: Iterable[str],
	left_label: str,
	right_label: str,
	title: str,
	output_file: Path,
) -> None:
	available = [m for m in metrics if f"{m}_a" in pairs.columns and f"{m}_reduced" in pairs.columns]
	if not available or pairs.empty:
		return

	n = len(available)
	fig, axes = plt.subplots(1, n, figsize=(3.4 * n, 4.2), constrained_layout=True)
	if n == 1:
		axes = [axes]

	for ax, m in zip(axes, available):
		left_vals = pairs[f"{m}_a"].dropna().values
		right_vals = pairs[f"{m}_reduced"].dropna().values
		if len(left_vals) == 0 and len(right_vals) == 0:
			ax.axis("off")
			continue
		ax.boxplot([left_vals, right_vals], tick_labels=[left_label, right_label], widths=0.55)
		ax.set_title(m)
		ax.grid(axis="y", alpha=0.25)

	if title:
		fig.suptitle(title)
	fig.savefig(output_file, dpi=180)
	plt.close(fig)


def plot_learning_effect(first_second: pd.DataFrame, output_file: Path) -> None:
	metrics = [
		"nasa_workload_5d",
		"performance",
		"confidence",
		"evidence_findability",
		"step_pinpointing",
	]
	available = [m for m in metrics if f"{m}_first" in first_second.columns]
	if not available:
		return

	n = len(available)
	fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 4.2), constrained_layout=True)
	if n == 1:
		axes = [axes]

	for ax, m in zip(axes, available):
		first_vals = first_second[f"{m}_first"].dropna().values
		second_vals = first_second[f"{m}_second"].dropna().values
		ax.boxplot([first_vals, second_vals], tick_labels=["First", "Second"], widths=0.55)
		ax.set_title(m)
		ax.grid(axis="y", alpha=0.25)
	fig.suptitle("Learning Effect: First vs Second Usage")
	fig.savefig(output_file, dpi=180)
	plt.close(fig)


def print_key_findings(cond_summary: pd.DataFrame, learn_summary: pd.DataFrame) -> None:
	print("\n=== Condition Effect (A vs Reduced) ===")
	core = cond_summary[cond_summary["metric"].isin(["nasa_workload_5d", "performance", "confidence"])].copy()
	if core.empty:
		print("No condition summary available.")
	else:
		print(core.to_string(index=False))

	print("\n=== First vs Second Usage (Learning) ===")
	core_l = learn_summary[
		learn_summary["metric"].isin(["nasa_workload_5d", "performance", "confidence"])
	].copy()
	if core_l.empty:
		print("No learning-effect summary available.")
	else:
		print(core_l.to_string(index=False))


def print_targeted_findings(
	full_vs_ablated_summary: pd.DataFrame,
	ab_summary: pd.DataFrame,
	ac_summary: pd.DataFrame,
) -> None:
	print("\n=== Full (A) vs Ablated (B/C): NASA + Shared Metrics ===")
	if full_vs_ablated_summary.empty:
		print("No full-vs-ablated summary available.")
	else:
		print(full_vs_ablated_summary.to_string(index=False))

	print("\n=== AB (A vs B): Image-Hash Structural-Alignment Questions ===")
	if ab_summary.empty:
		print("No AB-specific summary available.")
	else:
		print(ab_summary.to_string(index=False))

	print("\n=== AC (A vs C): Agentic-Judge Evidence-Visualization Questions ===")
	if ac_summary.empty:
		print("No AC-specific summary available.")
	else:
		print(ac_summary.to_string(index=False))


def main() -> None:
	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

	dag = load_survey(DAG_PATH, source_name="dag")
	evidence = load_survey(EVIDENCE_PATH, source_name="evidence")
	profile = load_profile()

	all_data = pd.concat([dag, evidence], ignore_index=True, sort=False)
	all_data = all_data.merge(profile, on="user_id", how="left")

	all_data.to_csv(OUTPUT_DIR / "combined_cleaned_data.csv", index=False)

	metrics = get_metric_columns(all_data)

	pairs = build_pairs_by_condition(all_data)
	pairs.to_csv(OUTPUT_DIR / "paired_condition_data.csv", index=False)

	cond_summaries = []
	for source_name in ["dag", "evidence"]:
		scope_pairs = pairs[pairs["source"] == source_name].copy()
		cond_summaries.append(summarize_condition_effect(scope_pairs, metrics, scope=source_name))
	cond_summaries.append(summarize_condition_effect(pairs, metrics, scope="pooled"))
	cond_summary = pd.concat(cond_summaries, ignore_index=True)
	cond_summary.to_csv(OUTPUT_DIR / "condition_effect_summary.csv", index=False)

	# 1) Full (A) vs Ablated (B/C): NASA + any metric shared by both B and C.
	shared_metrics = select_shared_metrics_between_ab_and_ac(pairs, metrics)
	primary_metrics = [m for m in CORE_SHARED_METRICS if m in shared_metrics]
	extra_shared = [m for m in shared_metrics if m not in CORE_SHARED_METRICS]
	full_vs_ablated_metrics = primary_metrics + extra_shared
	full_vs_ablated_summary = summarize_condition_effect(
		pairs,
		full_vs_ablated_metrics,
		scope="full_vs_ablated_pooled",
	)
	full_vs_ablated_summary.to_csv(OUTPUT_DIR / "full_vs_ablated_shared_summary.csv", index=False)

	# 2) AB specific (A vs B): image-hash structural-alignment related questions.
	ab_pairs = pairs[(pairs["source"] == "dag") & (pairs["reduced_condition"] == CONDITION_B)].copy()
	ab_metrics = [m for m in AB_UNIQUE_METRICS if f"{m}_diff_a_minus_reduced" in ab_pairs.columns]
	ab_summary = summarize_condition_effect(ab_pairs, ab_metrics, scope="ab_A_vs_B")
	ab_summary.to_csv(OUTPUT_DIR / "ab_unique_summary.csv", index=False)

	# 3) AC specific (A vs C): agentic-judge evidence-visualization related questions.
	ac_pairs = pairs[
		(pairs["source"] == "evidence") & (pairs["reduced_condition"] == CONDITION_C)
	].copy()
	ac_metrics = [m for m in AC_UNIQUE_METRICS if f"{m}_diff_a_minus_reduced" in ac_pairs.columns]
	ac_summary = summarize_condition_effect(ac_pairs, ac_metrics, scope="ac_A_vs_C")
	ac_summary.to_csv(OUTPUT_DIR / "ac_unique_summary.csv", index=False)

	first_second = build_first_second_pairs(all_data)
	first_second.to_csv(OUTPUT_DIR / "first_second_pairs.csv", index=False)

	learn_summary = summarize_learning_effect(first_second, metrics)
	learn_summary.to_csv(OUTPUT_DIR / "learning_effect_summary.csv", index=False)

	plot_core_metrics_by_condition(all_data, OUTPUT_DIR / "condition_effect_boxplots.png")
	plot_learning_effect(first_second, OUTPUT_DIR / "learning_effect_boxplots.png")
	plot_paired_metrics(
		pairs,
		full_vs_ablated_metrics,
		left_label="A(full)",
		right_label="Ablated(B/C)",
		title="Full (A) vs Ablated (B/C): NASA + Shared Metrics",
		output_file=OUTPUT_DIR / "full_vs_ablated_shared_boxplots.png",
	)
	ab_non_nasa_metrics = select_non_nasa_metrics_for_pairs(
		ab_pairs,
		metrics,
		excluded_metrics=["confidence", "evidence_findability"],
	)
	ac_non_nasa_metrics = select_non_nasa_metrics_for_pairs(
		ac_pairs,
		metrics,
		excluded_metrics=["confidence"],
	)
	plot_paired_metrics(
		ab_pairs,
		ab_non_nasa_metrics,
		left_label="full system",
		right_label="Ablated",
		title="",
		output_file=OUTPUT_DIR / "ab_non_nasa_boxplots.png",
	)
	plot_paired_metrics(
		ac_pairs,
		ac_non_nasa_metrics,
		left_label="full system",
		right_label="Ablated",
		title="",
		output_file=OUTPUT_DIR / "ac_non_nasa_boxplots.png",
	)
	plot_paired_metrics(
		ab_pairs,
		ab_metrics,
		left_label="A(full)",
		right_label="B(ablated)",
		title="AB: Effect of Image-Hash Structural Alignment",
		output_file=OUTPUT_DIR / "ab_unique_boxplots.png",
	)
	plot_paired_metrics(
		ac_pairs,
		ac_metrics,
		left_label="A(full)",
		right_label="C(ablated)",
		title="AC: Effect of Agentic-Judge Evidence Visualization",
		output_file=OUTPUT_DIR / "ac_unique_boxplots.png",
	)
	print_targeted_findings(full_vs_ablated_summary, ab_summary, ac_summary)
	print_key_findings(cond_summary, learn_summary)
	print("\nAnalysis files saved to:", OUTPUT_DIR)


if __name__ == "__main__":
	main()
