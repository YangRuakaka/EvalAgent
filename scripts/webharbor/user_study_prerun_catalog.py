"""Three new-domain pre-run cases for the CHI user-study extension.

Each dataset is one fixed task evaluated under four personas.  The task text,
model, website snapshot, and execution settings stay fixed within a dataset;
only the persona changes.
"""

from __future__ import annotations

from typing import Any


FINAL_REPORT_INSTRUCTIONS = (
    "Compare at least four task-valid candidates before choosing. Base every "
    "comparison on information visibly shown on the website; do not infer missing "
    "attributes. In the final answer, include a compact comparison table and end "
    "with three plain-text lines beginning exactly `FINAL RECOMMENDATION:`, "
    "`TRADE-OFF BASIS:`, and `VISIBLE EVIDENCE:`. Do not perform the site's "
    "transactional action."
)


DATASETS: list[dict[str, Any]] = [
    {
        "dataset": "data1",
        "case_id": "CHI-NEW-REC",
        "domain": "Cooking and recipe selection",
        "site": "Allrecipes",
        "url": "http://localhost:40000",
        "reset_url": "http://localhost:8101/reset/allrecipes",
        "task_name": "Choose one dessert recipe for a small dinner",
        "task": (
            "Choose one dessert recipe for a small dinner. "
            "Do not save, rate, review, or submit anything."
        ),
        "personas": [
            {
                "persona_id": "conformity",
                "value": "Conformity",
                "content": (
                    "Maya values belonging and prefers choices that are likely to feel "
                    "acceptable to most people. When uncertain, she is more comfortable "
                    "following a broadly shared preference than standing out."
                ),
            },
            {
                "persona_id": "convenience",
                "value": "Convenience",
                "content": (
                    "Maya values ease and prefers choices that minimize time, effort, and "
                    "complexity. She readily gives up some novelty or prestige for a "
                    "smoother experience."
                ),
            },
            {
                "persona_id": "innovation",
                "value": "Innovation",
                "content": (
                    "Maya is curious about unfamiliar possibilities and enjoys choices "
                    "that feel fresh or distinctive. She accepts some uncertainty when it "
                    "creates an opportunity to discover something new."
                ),
            },
            {
                "persona_id": "aesthetic_expression",
                "value": "Aesthetic Expression",
                "content": (
                    "Maya values beauty and self-expression and pays close attention to "
                    "how a choice looks and feels. She is willing to accept extra effort "
                    "when the result seems more visually memorable."
                ),
            },
        ],
    },
    {
        "dataset": "data2",
        "case_id": "CHI-NEW-EDU",
        "domain": "Online learning and course selection",
        "site": "Coursera",
        "url": "http://localhost:40013",
        "reset_url": "http://localhost:8101/reset/coursera",
        "task_name": "Choose one introductory AI course",
        "task": (
            "Choose one introductory AI course. "
            "Do not enroll, start a trial, or purchase anything."
        ),
        "personas": [
            {
                "persona_id": "convenience",
                "value": "Convenience",
                "content": (
                    "Jordan values ease and prefers choices that minimize time, effort, "
                    "and complexity. Jordan readily gives up some novelty or prestige for "
                    "a smoother experience."
                ),
            },
            {
                "persona_id": "mastery",
                "value": "Mastery",
                "content": (
                    "Jordan values mastery and prefers choices that support deep, sustained "
                    "understanding rather than quick familiarity. Jordan is willing to "
                    "invest substantially more effort for an option that appears "
                    "comprehensive and demanding."
                ),
            },
            {
                "persona_id": "innovation",
                "value": "Innovation",
                "content": (
                    "Jordan values novelty and actively looks beyond familiar mainstream "
                    "choices for ideas that reflect recent change. Jordan accepts lower "
                    "popularity and greater uncertainty when an option offers access to an "
                    "emerging direction."
                ),
            },
            {
                "persona_id": "benevolence",
                "value": "Benevolence",
                "content": (
                    "Jordan cares about improving other people's wellbeing and wants "
                    "personal choices to contribute to a broader social good. Jordan is "
                    "willing to accept extra effort when an option offers a clearer benefit "
                    "to others."
                ),
            },
        ],
    },
    {
        "dataset": "data3",
        "case_id": "CHI-NEW-MLM",
        "domain": "Machine-learning model selection",
        "site": "Hugging Face",
        "url": "http://localhost:40010",
        "reset_url": "http://localhost:8101/reset/huggingface",
        "task_name": "Choose one sentiment-analysis model for a prototype",
        "task": (
            "Choose one sentiment-analysis model for a prototype. "
            "Do not download, deploy, or modify anything."
        ),
        "personas": [
            {
                "persona_id": "sustainability",
                "value": "Sustainability",
                "content": (
                    "Riley values long-term environmental responsibility and tries to avoid "
                    "unnecessary consumption of energy or resources. Riley accepts some "
                    "loss of status or maximum performance when a lighter option is "
                    "sufficient."
                ),
            },
            {
                "persona_id": "conformity",
                "value": "Conformity",
                "content": (
                    "Riley values belonging and prefers choices that are already accepted "
                    "by a broad community. When uncertain, Riley feels more comfortable "
                    "following an established preference than choosing an obscure "
                    "alternative."
                ),
            },
            {
                "persona_id": "innovation",
                "value": "Innovation",
                "content": (
                    "Riley values novelty and believes unfamiliar possibilities deserve closer "
                    "examination rather than a quick judgment. Riley accepts uncertainty and "
                    "extra effort when exploring a more recent or distinctive direction."
                ),
            },
            {
                "persona_id": "nuance",
                "value": "Nuance",
                "content": (
                    "Riley values nuance and believes important judgments should preserve "
                    "subtle differences rather than flatten them. Riley prefers choices "
                    "that can handle ambiguity, even when they are less conventional."
                ),
            },
        ],
    },
]


def iter_runs() -> list[dict[str, Any]]:
    """Return one flattened run declaration per dataset/persona pair."""

    runs: list[dict[str, Any]] = []
    for dataset in DATASETS:
        for index, persona in enumerate(dataset["personas"], start=1):
            runs.append(
                {
                    **{key: value for key, value in dataset.items() if key != "personas"},
                    "run_index": index,
                    "run_id": f"{dataset['case_id']}-{index:02d}-{persona['persona_id']}",
                    "persona": persona,
                }
            )
    return runs


def validate_catalog() -> None:
    """Fail early if the within-case experimental controls are malformed."""

    if [dataset["dataset"] for dataset in DATASETS] != ["data1", "data2", "data3"]:
        raise ValueError("The UI requires exactly data1, data2, and data3")
    for dataset in DATASETS:
        personas = dataset["personas"]
        if len(personas) != 4:
            raise ValueError(f"{dataset['dataset']} must contain exactly four personas")
        values = [persona["value"] for persona in personas]
        if len(set(values)) != 4:
            raise ValueError(f"{dataset['dataset']} persona values must be unique")
        if not dataset["task"].strip():
            raise ValueError(f"{dataset['dataset']} task must not be empty")


validate_catalog()
