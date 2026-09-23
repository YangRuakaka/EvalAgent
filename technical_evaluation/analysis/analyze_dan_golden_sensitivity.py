"""Audit Dan versus the fixed golden verdicts without changing any labels.

Run from any directory: python3 -B path/to/analyze_dan_golden_sensitivity.py
Outputs a reproducible JSON audit and a Markdown report next to published metrics.
The golden export is a FINAL reference, not independent pre-adjudication labels.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import compare_criteria1_agreement as metrics
import compute_golden72_metrics as pooled


ROOT = Path(__file__).resolve().parents[2]
TE = ROOT / "technical_evaluation"
REPORT = TE / "results/webharbor105_final_metrics.json"
DAN = TE / "experiments/march_binary_dan48/dan_criteria1_annotations.json"
OUTPUT = TE / "results/dan_golden_verdict_sensitivity"
NAMES = {
    "agentic_gpt5": "Agentic GPT-5",
    "baseline_gpt5": "Baseline GPT-5",
    "agentic_deepseek": "Agentic DeepSeek",
    "baseline_deepseek": "Baseline DeepSeek",
}

# Interpretations of selected evidence, NOT explanations supplied by annotators.
NOTES = {
    "FLT-02-A": "两人对同一末步给出相反标签。争议点是选择便宜直飞是否已充分满足 convenience，还是应优先更短的直飞；golden 选段同时记录了更短的 United 选项。",
    "FLT-03-C": "criteria1 要求优先较低排放，但执行 persona 是 Convenience。Dan 选中的直飞/低价理由可能说明方便，却未直接证明较低排放标准得到满足。需确认标注时以哪个标准为准。",
    "HOT-02-A": "criteria1 涉及免费取消及位置/通达性。golden 强调免费取消、最高评分和减少浏览；Dan 对评分驱动的最终选择标 fail。需核对位置/通达性是否实际参与选择。",
    "HOT-03-B": "criteria1 要求基于评分/评论的广泛验证，persona 是 Health。相同健身/健康设施选段在 Dan 中为 pass、golden 中为 fail；最终推荐也报告评分，应复核这些因素在决策中的权重。不能仅因推荐有健康设施就判定 golden 错误。",
    "INF-01-C": "criteria1 要求 foundational/earlier/established contribution。选段显示 agent 先认为 Poly-encoders 不适合入门，后又把它解释为基础介绍；需区分入门适用性与该明确 criterion，二者并不等同。",
    "MLM-02-B": "优先复核：golden 总 verdict 为 fail，但其全部 5 条 evidence 及两个已标步骤都是 pass，overall_reasoning 为空。criteria1 要求即时可用的推理界面；轨迹既按热度选择，也验证了界面，需说明为什么这些 pass 证据仍导向 fail。",
    "REC-01-C": "criteria1 要求 established/classic preparation，persona 是 Thoroughness。golden 引用家庭晚餐适用性、评论及信息完整性；这些是否充分证明 classic/proven preparation 尚需说明。",
    "RET-01-B": "优先复核：criteria1 是比较价格并偏向更低成本，persona 却是 Innovation。Dan 标 pass，golden 对选 HP 而不选更新 MacBook 的证据标 fail；可能涉及评估 criterion 与 persona 的混用，不能把这种解释当作已确认原因。",
    "RET-02-A": "criteria1 要求依据明确环境/材料影响信息偏向低影响选项。golden 接受报告 PVC 的环境问题并解释任务约束；Dan 对没有环保声明、仍选择 PVC 标 fail。分歧可能在于识别问题是否足以满足实际选择要求。",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load_predictions(folder):
    result, records, paths = {}, {}, []
    for path in sorted(folder.glob("*__evaluated.json")):
        record = read(path)
        cid = str(record["data_id"])
        if cid in result:
            raise ValueError(f"Duplicate {cid} in {folder}")
        item = metrics._extract_criteria1_result(record) or {}
        result[cid] = str(item.get("overall_assessment") or "missing").strip().lower()
        records[cid] = record
        paths.append(fingerprint(path))
    return result, records, paths


def exact_p(b, c):
    n = b + c
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2**n) if n else 1.0


def score(ids, labels, predictions):
    ids = sorted(ids)
    systems = {}
    for name, pred in predictions.items():
        correct = sum(pred.get(cid) == labels[cid] for cid in ids)
        systems[name] = {
            "correct": correct, "n": len(ids), "accuracy": correct / len(ids),
            "wilson_95_ci": pooled._wilson_interval(correct, len(ids)),
            "missing_or_unknown": sum(pred.get(cid) not in ("pass", "fail") for cid in ids),
        }
    tests = {}
    for family in ("gpt5", "deepseek"):
        a, b = predictions[f"agentic_{family}"], predictions[f"baseline_{family}"]
        a_only = sum(a.get(cid) == labels[cid] and b.get(cid) != labels[cid] for cid in ids)
        b_only = sum(b.get(cid) == labels[cid] and a.get(cid) != labels[cid] for cid in ids)
        tests[family] = {
            "agentic_only_correct": a_only, "baseline_only_correct": b_only,
            "agentic_minus_baseline_percentage_points": 100 * (a_only - b_only) / len(ids),
            "mcnemar_exact_two_sided_p_unadjusted": exact_p(a_only, b_only),
        }
    return {"n": len(ids), "case_ids": ids, "gold_distribution": dict(Counter(labels[i] for i in ids)),
            "systems": systems, "paired_tests": tests}


def main():
    published = read(REPORT)
    new_path = Path(published["new_human_file"])
    old_path = Path(published["old_human_file"])
    overlay_path = Path(published["baseline_gpt_old_metrics_overlay"])
    gold_raw, dan_raw = read(new_path), read(DAN)
    gold = metrics._load_human_cases(new_path)
    old = metrics._load_human_cases(old_path)
    dan = metrics._load_human_cases(DAN)
    assert len(gold) == 72 and len(old) == 33 and len(dan) == 48
    assert not (gold.keys() & old.keys()) and set(dan) <= set(gold)
    # Preserve the already published binary adjudication; never write it to input.
    adjudication = published["binary_adjudication"]
    old[adjudication["case_id"]]["overall_assessment"] = adjudication["final_human_verdict"]
    labels = {cid: item["overall_assessment"] for cid, item in (old | gold).items()}
    assert set(labels.values()) <= {"pass", "fail"}
    assert all(v["overall_assessment"] in ("pass", "fail") for v in dan.values())

    old_sources = read(overlay_path)["sources"]
    old_dirs = {"agentic_gpt5": Path(old_sources["gpt_dir"]),
                "agentic_deepseek": Path(old_sources["deepseek_dir"]),
                "baseline_gpt5": Path(old_sources["baseline_gpt_dir"]),
                "baseline_deepseek": Path(old_sources["baseline_deepseek_dir"])}
    new_dirs = dict(pooled.SYSTEMS)
    new_dirs["baseline_gpt5"] = Path(published["baseline_gpt_new_results_dir"])
    predictions, records, sources, reproduction = {}, {}, {}, {}
    for name in NAMES:
        op, _, oh = load_predictions(old_dirs[name])
        np, nr, nh = load_predictions(new_dirs[name])
        assert set(op) == set(old) and set(np) == set(gold), name
        assert sum(np[cid] == labels[cid] for cid in gold) == published["new_72"]["systems"][name]["correct_final_verdict_count"]
        predictions[name], records[name] = op | np, nr
        actual = sum(predictions[name][cid] == labels[cid] for cid in labels)
        expected_total = published["combined_105"]["systems"][name]["correct_final_verdict_count"]
        reproduction[name] = {"available_raw_outputs_correct105": actual,
                              "published_correct105": expected_total,
                              "matches": actual == expected_total,
                              "old33_prediction_distribution": dict(Counter(op.values()))}
        sources[name] = {"old_directory": str(old_dirs[name]), "new_directory": str(new_dirs[name]), "files": oh + nh}

    shared = sorted(dan)
    disagreements = [cid for cid in shared if dan[cid]["overall_assessment"] != labels[cid]]
    agreement = sorted(set(shared) - set(disagreements))
    raw_cases = {cid: read(TE / f"annotation/webharbor_72_human/Dan/raw_data/{cid}.json") for cid in shared}
    content_checks = []
    text_fields = ("step_id", "EVALUATION", "MEMORY", "AI REASONING", "TARGET OBJECTIVE", "ACTION")
    for cid, raw in raw_cases.items():
        for name in NAMES:
            rec = records[name][cid]
            same_steps = [tuple(s.get(f) for f in text_fields) for s in raw["steps"]] == [tuple(s.get(f) for f in text_fields) for s in rec["steps"]]
            content_checks.append({"case_id": cid, "system": name,
                                   "same_criterion": raw.get("criteria1") == rec.get("criteria1"),
                                   "same_task": raw.get("task") == rec.get("task"),
                                   "same_step_text": same_steps})
    direct_yukun = [cid for cid in shared if str(raw_cases[cid].get("co_annotator", "")).lower() == "yukun"]
    cohorts = {
        "webharbor72": score(gold, labels, predictions),
        "dan_golden_shared48": score(shared, labels, predictions),
        "dan_golden_agreement_only": score(agreement, labels, predictions),
        "dan_golden_disagreements": score(disagreements, labels, predictions),
        "webharbor72_excluding_known_disagreements": score(set(gold) - set(disagreements), labels, predictions),
        "shared48_using_dan_verdicts": score(shared, {cid: dan[cid]["overall_assessment"] for cid in shared}, predictions),
        "original_dan_yukun_assignment_vs_final_golden": score(direct_yukun, labels, predictions),
    }
    # The stored old33 DeepSeek baseline aggregate differs from the available
    # historical prediction files. Preserve the published aggregate, subtract
    # verified discrepant-case contributions, and do NOT invent paired outcomes.
    for key, excluded in (("published_full105", []),
                          ("published_full105_excluding_known_disagreements", disagreements)):
        systems = {}
        for name in NAMES:
            correct = published["combined_105"]["systems"][name]["correct_final_verdict_count"] - sum(predictions[name][cid] == labels[cid] for cid in excluded)
            n = len(labels) - len(excluded)
            systems[name] = {"correct": correct, "n": n, "accuracy": correct/n,
                             "wilson_95_ci": pooled._wilson_interval(correct,n)}
        cohorts[key] = {"n": n, "systems": systems, "paired_tests": {},
                        "method": "published aggregate minus verified excluded-case contributions; historical baseline DeepSeek discrepancy unresolved"}
    pairs = Counter((dan[cid]["overall_assessment"], labels[cid]) for cid in shared)
    observed = len(agreement) / len(shared)
    expected = sum(sum(dan[cid]["overall_assessment"] == v for cid in shared) * sum(labels[cid] == v for cid in shared) for v in ("pass", "fail")) / len(shared)**2
    details = []
    for cid in disagreements:
        raw = raw_cases[cid]
        details.append({"case_id": cid, "dan_verdict": dan[cid]["overall_assessment"], "golden_verdict": labels[cid],
                        "criterion": raw["criteria1"], "task": raw["task"], "persona_value": raw["persona_value"],
                        "original_co_annotator": raw.get("co_annotator"),
                        "model_verdicts": {name: predictions[name][cid] for name in NAMES},
                        "dan_annotation": dan_raw["annotations"][cid], "golden_annotation": gold_raw["annotations"][cid],
                        "interpretation_not_annotator_explanation": NOTES[cid]})
    audit = {
        "scope": "Dan versus user-identified Yukun final golden reference; not pre-adjudication inter-annotator reliability",
        "inputs": [fingerprint(p) for p in (REPORT, DAN, new_path, old_path, overlay_path)],
        "prediction_sources": sources,
        "published_72_case_verdict_counts_reproduced": True,
        "published_105_case_reproduction": reproduction,
        "preserved_published_binary_adjudication": adjudication,
        "shared_n": len(shared), "disagreement_n": len(disagreements), "agreement_n": len(agreement),
        "agreement_rate": observed, "cohens_kappa_descriptive_vs_final_reference": (observed-expected)/(1-expected),
        "label_pairs_dan_then_golden": {f"{a}/{b}": n for (a,b),n in pairs.items()},
        "original_co_annotator_counts": dict(Counter(raw_cases[cid].get("co_annotator") for cid in shared)),
        "original_dan_yukun_assigned_disagreements": sorted(set(direct_yukun) & set(disagreements)),
        "input_content_checks": content_checks, "cohorts": cohorts, "disagreements": details,
        "limitations": ["Final golden labels are not Yukun's independent pre-adjudication annotation export.",
                        "No old33 Dan annotation export was used; those cases are outside this pairwise audit.",
                        "The remaining 96 cases include 57 without a Dan comparison; do not call all 96 consensus cases.",
                        "No annotation or published metric was changed; this audit addresses verdicts, not evidence-set adjudication.",
                        "Available old33 baseline DeepSeek files reproduce 19 correct versus 21 implied by the published aggregate. The 105/96 results therefore preserve the published aggregate, subtract verified excluded cases, and do not provide unverified full-benchmark paired tests.",
                        "Case explanations are analyst interpretations of selected evidence; both exports lack overall reasoning for the nine discrepant cases.",
                        "Exact McNemar p-values are two-sided, exploratory and unadjusted for multiple comparisons."]}
    OUTPUT.with_suffix(".json").write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

    lines = ["# Dan–golden verdict sensitivity audit", "", "## Scope and provenance", "",
             "Yukun is identified with the final golden export as requested by the user. This is a comparison against a final reference, not an estimate of pre-adjudication disagreement.", "",
             f"Shared cases: **{len(shared)}**; agreements: **{len(agreement)}**; disagreements: **{len(disagreements)}** ({100*len(disagreements)/len(shared):.2f}%). Agreement = {100*observed:.2f}%; descriptive Cohen's κ against final golden = {(observed-expected)/(1-expected):.3f}.", "",
             f"Original co-annotator assignments: {audit['original_co_annotator_counts']}. Disagreements in the original Dan/Yukun assignment: {audit['original_dan_yukun_assigned_disagreements']}.", "",
             "All four published 72-case verdict counts were reproduced from saved model outputs. Three of four 105-case counts reproduce; historical baseline DeepSeek gives 78/105 rather than published 80/105 (19 rather than 21 correct on old33). The published 105/96 rows below preserve the published totals and subtract verified excluded-case contributions. They are conditional aggregate calculations, not a complete reproduction. Missing/unknown/partial outputs count as incorrect for binary golden labels. The existing data_000032 binary adjudication is preserved.", "",
             f"Input comparisons (Dan raw data versus four model record sets): {sum(all(c[k] for k in ('same_criterion','same_task','same_step_text')) for c in content_checks)}/{len(content_checks)} have matching criterion, task and trajectory text.", "",
             "## Accuracy", "", "| Evaluation set | n | Agentic GPT-5 | Baseline GPT-5 | Agentic DeepSeek | Baseline DeepSeek |", "|---|---:|---:|---:|---:|---:|"]
    for key, cohort in cohorts.items():
        cells = [f"{x['correct']}/{x['n']} ({100*x['accuracy']:.2f}%)" for x in cohort["systems"].values()]
        lines.append(f"| {key} | {cohort['n']} | " + " | ".join(cells) + " |")
    lines += ["", "## Paired tests", "", "Two-sided exact McNemar tests; unadjusted exploratory p-values. Positive differences favor Agentic Judge.", "",
              "| Evaluation set | Model | Agentic − baseline (pp) | Agentic-only correct | Baseline-only correct | p |", "|---|---|---:|---:|---:|---:|"]
    for key in ("webharbor72", "dan_golden_shared48", "dan_golden_agreement_only", "webharbor72_excluding_known_disagreements"):
        for family, v in cohorts[key]["paired_tests"].items():
            lines.append(f"| {key} | {family} | {v['agentic_minus_baseline_percentage_points']:+.2f} | {v['agentic_only_correct']} | {v['baseline_only_correct']} | {v['mcnemar_exact_two_sided_p_unadjusted']:.6f} |")
    lines += ["", "## Interpretation", "",
              "在共享的 48 个 cases 上，两个模型家族的 Agentic Judge 与各自 baseline 准确率相同。排除 9 个分歧后，在 39 个一致案例上，两种 baseline 均比对应 Agentic Judge 多答对 1 个；不能声称 Agentic Judge 的优势在一致子集上仍然成立。", "",
              "按已发表汇总值从完整 105 cases 扣除已识别的 9 个分歧，剩余 96 cases 仍显示 Agentic Judge 的总体准确率优势。但其中 57 cases 未经过此次 Dan 对照，不能把 96 cases 称为全部经双方一致确认的样本；历史 baseline DeepSeek 的原始预测与汇总不一致亦需另行核对。", "",
              "以下逐例解读基于 evidence selections 和原始 criterion，不是标注者提供的解释。九例均缺少明确 overall reasoning。保持 golden 不变，先复核标注依据。", "",
              "## Disagreement cases", "", "| Case | Dan | Golden | Persona | Review note |", "|---|---|---|---|---|"]
    for d in details:
        lines.append(f"| {d['case_id']} | {d['dan_verdict']} | {d['golden_verdict']} | {d['persona_value']} | {NOTES[d['case_id']]} |")
    for d in details:
        lines += ["", f"### {d['case_id']}", "", f"Task: {d['task']}", "", f"Evaluation criterion: **{d['criterion']}**", "",
                  f"Execution persona: {d['persona_value']}. Original co-annotator: {d['original_co_annotator']}.", "",
                  "Model verdicts: " + "; ".join(f"{NAMES[k]}: {v}" for k,v in d['model_verdicts'].items()), "", NOTES[d['case_id']], ""]
        for name, annotation in (("Dan", d["dan_annotation"]), ("Golden", d["golden_annotation"])):
            lines += [f"#### {name}: {annotation['overall_assessment']}", "", "Overall reasoning: " + (annotation.get("overall_reasoning") or "[not recorded]"), ""]
            for e in annotation.get("evidences", []):
                lines.append(f"- Step {e['step_id']}, {e['field']}, {e.get('verdict')}: " + json.dumps(e.get("text", ""), ensure_ascii=False))
            lines.append("")
    lines += ["## Limitations", ""] + [f"- {x}" for x in audit["limitations"]]
    lines += ["", "## Source files", ""] + [f"- `{x['path']}` — SHA-256 `{x['sha256']}`" for x in audit["inputs"]]
    OUTPUT.with_suffix(".md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps({"shared": len(shared), "disagreements": disagreements,
                      "original_assignments": audit['original_co_annotator_counts'],
                      "original_dan_yukun_assigned_disagreements": audit['original_dan_yukun_assigned_disagreements'],
                      "reproduction": reproduction,
                      "content_mismatches": [c for c in content_checks if not all(c[k] for k in ('same_criterion','same_task','same_step_text'))],
                      "cohorts": {k: {"n": c['n'], "systems": c['systems'], "paired_tests": c['paired_tests']} for k,c in cohorts.items()},
                      "outputs": [str(OUTPUT.with_suffix(ext)) for ext in ('.json','.md')]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
