from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


DEFAULT_FILES = [
	"user_study_analysis/results/DAG/P06_condition_B.json",
	"user_study_analysis/results/DAG/P06_condition_A.json",
	"user_study_analysis/results/DAG/P04_condition_B.json",
	"user_study_analysis/results/DAG/P04_condition_A.json",
	"user_study_analysis/results/DAG/P02_condition_B.json",
	"user_study_analysis/results/DAG/P02_condition_A.json",
]

FILENAME_PATTERN = re.compile(r"(?P<participant>P\d+)_condition_(?P<condition>[AB])\.json$")


@dataclass
class SessionStats:
	participant: str
	condition: str
	file_path: Path
	total_events: int
	duration_seconds: float
	counts_by_type: dict[str, int]
	mouse_points: list[tuple[float, float]]


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Compare DAG interaction behavior between condition A and condition B."
	)
	parser.add_argument(
		"--files",
		nargs="+",
		default=DEFAULT_FILES,
		help="List of DAG interaction JSON files to compare.",
	)
	parser.add_argument(
		"--output-dir",
		default="user_study_analysis/results/DAG/analysis_outputs",
		help="Directory where CSV summaries and heatmap image are saved.",
	)
	return parser.parse_args()


def load_session_stats(file_path: Path) -> SessionStats:
	match = FILENAME_PATTERN.search(file_path.name)
	if not match:
		raise ValueError(f"Unexpected filename format: {file_path}")

	participant = match.group("participant")
	condition = match.group("condition")

	with file_path.open("r", encoding="utf-8") as f:
		payload = json.load(f)

	interactions = payload.get("interactions", [])
	counts_from_interactions = Counter(event.get("type", "unknown") for event in interactions)

	summary = payload.get("summary", {})
	summary_counts = summary.get("countsByType", {})

	if counts_from_interactions:
		counts_by_type = dict(counts_from_interactions)
	else:
		counts_by_type = {str(k): int(v) for k, v in summary_counts.items()}

	total_events = int(summary.get("totalEvents", payload.get("count", len(interactions))))
	duration_seconds = float(summary.get("sessionDurationSeconds", 0.0))

	mouse_points: list[tuple[float, float]] = []
	for event in interactions:
		if event.get("scope") != "trajectory_dag":
			continue

		x = event.get("x")
		y = event.get("y")
		w = event.get("containerWidth")
		h = event.get("containerHeight")
		if x is None or y is None or not w or not h:
			continue

		x_norm = float(x) / float(w)
		y_norm = float(y) / float(h)

		# Clamp points that slightly exceed the container boundary during logging.
		x_norm = max(0.0, min(1.0, x_norm))
		y_norm = max(0.0, min(1.0, y_norm))
		mouse_points.append((x_norm, y_norm))

	return SessionStats(
		participant=participant,
		condition=condition,
		file_path=file_path,
		total_events=total_events,
		duration_seconds=duration_seconds,
		counts_by_type=counts_by_type,
		mouse_points=mouse_points,
	)


def ensure_absolute_paths(paths: list[str], repo_root: Path) -> list[Path]:
	resolved: list[Path] = []
	for raw in paths:
		path = Path(raw)
		if not path.is_absolute():
			path = repo_root / path
		resolved.append(path)
	return resolved


def write_participant_summary_csv(
	grouped: dict[str, dict[str, SessionStats]], output_path: Path
) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", newline="", encoding="utf-8") as f:
		writer = csv.writer(f)
		writer.writerow(
			[
				"participant",
				"total_events_A",
				"total_events_B",
				"delta_total_B_minus_A",
				"duration_sec_A",
				"duration_sec_B",
				"delta_duration_B_minus_A",
			]
		)
		for participant in sorted(grouped):
			a = grouped[participant].get("A")
			b = grouped[participant].get("B")
			if not a or not b:
				continue
			writer.writerow(
				[
					participant,
					a.total_events,
					b.total_events,
					b.total_events - a.total_events,
					a.duration_seconds,
					b.duration_seconds,
					b.duration_seconds - a.duration_seconds,
				]
			)


def write_interaction_diff_csv(
	grouped: dict[str, dict[str, SessionStats]], output_path: Path
) -> tuple[list[str], list[str], np.ndarray]:
	interaction_types = sorted(
		{
			key
			for participant_sessions in grouped.values()
			for session in participant_sessions.values()
			for key in session.counts_by_type
		}
	)
	participants = sorted(grouped.keys())

	matrix = np.zeros((len(participants), len(interaction_types)), dtype=int)

	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", newline="", encoding="utf-8") as f:
		writer = csv.writer(f)
		writer.writerow(["participant", *interaction_types])

		for row_i, participant in enumerate(participants):
			a = grouped[participant].get("A")
			b = grouped[participant].get("B")

			if not a or not b:
				continue

			row = [participant]
			for col_i, interaction_type in enumerate(interaction_types):
				diff = b.counts_by_type.get(interaction_type, 0) - a.counts_by_type.get(interaction_type, 0)
				matrix[row_i, col_i] = diff
				row.append(diff)

			writer.writerow(row)

	return participants, interaction_types, matrix


def plot_heatmap(
	participants: list[str], interaction_types: list[str], matrix: np.ndarray, output_path: Path
) -> None:
	if matrix.size == 0:
		return

	fig_width = max(10, 0.55 * len(interaction_types))
	fig_height = max(4, 0.7 * len(participants))
	fig, ax = plt.subplots(figsize=(fig_width, fig_height))

	vmax = np.max(np.abs(matrix)) if np.max(np.abs(matrix)) > 0 else 1
	im = ax.imshow(matrix, cmap="RdBu_r", aspect="auto", vmin=-vmax, vmax=vmax)

	ax.set_xticks(np.arange(len(interaction_types)))
	ax.set_yticks(np.arange(len(participants)))
	ax.set_xticklabels(interaction_types, rotation=45, ha="right")
	ax.set_yticklabels(participants)
	ax.set_title("DAG interaction count differences (Condition B - Condition A)")
	ax.set_xlabel("Interaction Type")
	ax.set_ylabel("Participant")

	for i in range(matrix.shape[0]):
		for j in range(matrix.shape[1]):
			val = matrix[i, j]
			text_color = "white" if abs(val) > vmax * 0.45 else "black"
			ax.text(j, i, str(val), ha="center", va="center", color=text_color, fontsize=8)

	cbar = fig.colorbar(im, ax=ax)
	cbar.set_label("Count Difference (B - A)")

	fig.tight_layout()
	output_path.parent.mkdir(parents=True, exist_ok=True)
	fig.savefig(output_path, dpi=220)
	plt.close(fig)


def compute_mouse_density_grid(points: list[tuple[float, float]], bins: int = 40) -> np.ndarray:
	if not points:
		return np.zeros((bins, bins), dtype=float)

	x_vals = np.array([p[0] for p in points], dtype=float)
	y_vals = np.array([p[1] for p in points], dtype=float)
	grid, _, _ = np.histogram2d(y_vals, x_vals, bins=bins, range=[[0.0, 1.0], [0.0, 1.0]])
	return grid


def plot_mouse_position_heatmaps(
	grouped: dict[str, dict[str, SessionStats]], output_path: Path, bins: int = 40
) -> tuple[dict[str, int], dict[str, dict[str, float]]]:
	points_a: list[tuple[float, float]] = []
	points_b: list[tuple[float, float]] = []

	for participant in sorted(grouped):
		a = grouped[participant].get("A")
		b = grouped[participant].get("B")
		if a:
			points_a.extend(a.mouse_points)
		if b:
			points_b.extend(b.mouse_points)

	grid_a = compute_mouse_density_grid(points_a, bins=bins)
	grid_b = compute_mouse_density_grid(points_b, bins=bins)
	grid_diff = grid_b - grid_a

	fig, axes = plt.subplots(1, 3, figsize=(18, 5), constrained_layout=True)

	im0 = axes[0].imshow(grid_a, cmap="YlOrRd", origin="upper", extent=[0, 1, 1, 0], aspect="auto")
	axes[0].set_title(f"Condition A Mouse Density (n={len(points_a)})")
	axes[0].set_xlabel("x / width")
	axes[0].set_ylabel("y / height")
	fig.colorbar(im0, ax=axes[0], fraction=0.046)

	im1 = axes[1].imshow(grid_b, cmap="YlOrRd", origin="upper", extent=[0, 1, 1, 0], aspect="auto")
	axes[1].set_title(f"Condition B Mouse Density (n={len(points_b)})")
	axes[1].set_xlabel("x / width")
	axes[1].set_ylabel("y / height")
	fig.colorbar(im1, ax=axes[1], fraction=0.046)

	vmax = np.max(np.abs(grid_diff)) if np.max(np.abs(grid_diff)) > 0 else 1
	im2 = axes[2].imshow(
		grid_diff,
		cmap="RdBu_r",
		origin="upper",
		extent=[0, 1, 1, 0],
		aspect="auto",
		vmin=-vmax,
		vmax=vmax,
	)
	axes[2].set_title("Mouse Density Difference (B - A)")
	axes[2].set_xlabel("x / width")
	axes[2].set_ylabel("y / height")
	fig.colorbar(im2, ax=axes[2], fraction=0.046)

	for ax in axes:
		ax.set_xlim(0, 1)
		ax.set_ylim(1, 0)
		ax.axvline(0.5, color="white", linewidth=0.8, alpha=0.6)
		ax.axhline(0.5, color="white", linewidth=0.8, alpha=0.6)

	output_path.parent.mkdir(parents=True, exist_ok=True)
	fig.savefig(output_path, dpi=220)
	plt.close(fig)

	def quadrant_ratio(points: list[tuple[float, float]]) -> dict[str, float]:
		if not points:
			return {"top_left": 0.0, "top_right": 0.0, "bottom_left": 0.0, "bottom_right": 0.0}

		count = len(points)
		bins_count = {"top_left": 0, "top_right": 0, "bottom_left": 0, "bottom_right": 0}
		for x, y in points:
			if y < 0.5 and x < 0.5:
				bins_count["top_left"] += 1
			elif y < 0.5 and x >= 0.5:
				bins_count["top_right"] += 1
			elif y >= 0.5 and x < 0.5:
				bins_count["bottom_left"] += 1
			else:
				bins_count["bottom_right"] += 1

		return {k: (v / count) for k, v in bins_count.items()}

	return (
		{"A": len(points_a), "B": len(points_b)},
		{"A": quadrant_ratio(points_a), "B": quadrant_ratio(points_b)},
	)


def write_mouse_quadrant_csv(
	quadrant_stats: dict[str, dict[str, float]], output_path: Path
) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", newline="", encoding="utf-8") as f:
		writer = csv.writer(f)
		writer.writerow(["condition", "top_left", "top_right", "bottom_left", "bottom_right"])
		for condition in ["A", "B"]:
			stats = quadrant_stats.get(condition, {})
			writer.writerow(
				[
					condition,
					round(stats.get("top_left", 0.0), 4),
					round(stats.get("top_right", 0.0), 4),
					round(stats.get("bottom_left", 0.0), 4),
					round(stats.get("bottom_right", 0.0), 4),
				]
			)


def print_console_summary(grouped: dict[str, dict[str, SessionStats]]) -> None:
	print("\n=== DAG Interaction Comparison: Condition B vs A ===")
	for participant in sorted(grouped):
		a = grouped[participant].get("A")
		b = grouped[participant].get("B")
		if not a or not b:
			print(f"- {participant}: missing condition A or B; skipped.")
			continue

		delta_events = b.total_events - a.total_events
		delta_duration = b.duration_seconds - a.duration_seconds
		print(
			f"- {participant}: total_events A={a.total_events}, B={b.total_events}, "
			f"delta(B-A)={delta_events}; duration_sec A={a.duration_seconds:.1f}, "
			f"B={b.duration_seconds:.1f}, delta(B-A)={delta_duration:.1f}"
		)

		all_types = sorted(set(a.counts_by_type) | set(b.counts_by_type))
		diffs = []
		for t in all_types:
			diff = b.counts_by_type.get(t, 0) - a.counts_by_type.get(t, 0)
			if diff != 0:
				diffs.append((t, diff))

		if not diffs:
			print("  interaction diff: no difference by type")
			continue

		diffs.sort(key=lambda x: abs(x[1]), reverse=True)
		top = ", ".join(f"{name}:{delta:+d}" for name, delta in diffs[:5])
		print(f"  top interaction diffs: {top}")


def main() -> None:
	args = parse_args()

	script_path = Path(__file__).resolve()
	repo_root = script_path.parents[1]
	input_paths = ensure_absolute_paths(args.files, repo_root)

	grouped: dict[str, dict[str, SessionStats]] = defaultdict(dict)

	for path in input_paths:
		if not path.exists():
			raise FileNotFoundError(f"Input file not found: {path}")
		stats = load_session_stats(path)
		grouped[stats.participant][stats.condition] = stats

	output_dir = ensure_absolute_paths([args.output_dir], repo_root)[0]
	output_dir.mkdir(parents=True, exist_ok=True)

	participant_summary_csv = output_dir / "participant_summary.csv"
	interaction_diff_csv = output_dir / "interaction_diff_B_minus_A.csv"
	heatmap_png = output_dir / "interaction_diff_heatmap.png"
	mouse_heatmap_png = output_dir / "mouse_position_density_A_vs_B.png"
	mouse_quadrant_csv = output_dir / "mouse_quadrant_ratio_A_vs_B.csv"

	write_participant_summary_csv(grouped, participant_summary_csv)
	participants, interaction_types, matrix = write_interaction_diff_csv(grouped, interaction_diff_csv)
	plot_heatmap(participants, interaction_types, matrix, heatmap_png)
	mouse_point_counts, quadrant_stats = plot_mouse_position_heatmaps(grouped, mouse_heatmap_png)
	write_mouse_quadrant_csv(quadrant_stats, mouse_quadrant_csv)
	print_console_summary(grouped)

	print("\n=== Mouse-on-Graph Region Summary (normalized) ===")
	for condition in ["A", "B"]:
		stats = quadrant_stats.get(condition, {})
		main_area = max(stats, key=stats.get) if stats else "N/A"
		print(
			f"- Condition {condition}: points={mouse_point_counts.get(condition, 0)}, "
			f"top_left={stats.get('top_left', 0.0):.2%}, "
			f"top_right={stats.get('top_right', 0.0):.2%}, "
			f"bottom_left={stats.get('bottom_left', 0.0):.2%}, "
			f"bottom_right={stats.get('bottom_right', 0.0):.2%}, "
			f"main_area={main_area}"
		)

	print("\nSaved files:")
	print(f"- {participant_summary_csv}")
	print(f"- {interaction_diff_csv}")
	print(f"- {heatmap_png}")
	print(f"- {mouse_heatmap_png}")
	print(f"- {mouse_quadrant_csv}")


if __name__ == "__main__":
	main()
