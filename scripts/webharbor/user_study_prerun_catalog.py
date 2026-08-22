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
        "task_name": "Choose a dessert recipe for a small dinner gathering",
        "task": (
            "Find and recommend one dessert recipe for a small dinner gathering. "
            "For every candidate, collect the recipe title, rating/review count, "
            "preparation or total time, and one visible ingredient, dietary label, "
            "or preparation technique. "
            + FINAL_REPORT_INSTRUCTIONS
            + " Do not save, rate, review, or submit anything."
        ),
        "personas": [
            {
                "persona_id": "conformity",
                "value": "Conformity",
                "content": (
                    "Maya wants a dessert with strong visible social proof. Among valid "
                    "options, she prioritizes the combination of rating and review count, "
                    "favoring a widely reviewed choice over a faster, newer, or more "
                    "unusual recipe."
                ),
            },
            {
                "persona_id": "convenience",
                "value": "Convenience",
                "content": (
                    "Maya has limited time and energy before the gathering. Among valid "
                    "options, she prioritizes the shortest visible total or preparation "
                    "time and a low-effort technique such as no-bake or few preparation "
                    "steps, even when another option is more popular."
                ),
            },
            {
                "persona_id": "tradition",
                "value": "Tradition",
                "content": (
                    "Maya wants a familiar dessert that most guests will immediately "
                    "recognize. Among valid options, she favors a classic, established "
                    "recipe and conventional baking technique over novelty, even when a "
                    "less conventional recipe is faster."
                ),
            },
            {
                "persona_id": "innovation",
                "value": "Innovation",
                "content": (
                    "Maya wants the dessert to feel memorable and different. Among valid "
                    "options, she favors an unusual visible ingredient, combination, or "
                    "preparation technique over a familiar classic, provided the option "
                    "still fits the task."
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
        "task_name": "Choose an introductory course for practical AI skills",
        "task": (
            "Find and recommend one introductory course for a beginner who wants to "
            "develop practical AI skills. For every candidate, collect the title, "
            "provider, rating plus review or enrollment information, duration, and two "
            "visible topics, skills, labs, or projects. Record visible new-course "
            "information when present. A candidate is task-valid only when its title, "
            "description, or visible topics explicitly show an artificial intelligence, "
            "AI, machine learning, generative AI, or large-language-model focus. A "
            "general Python, programming, or data-science course without one of those "
            "visible AI/ML signals is not task-valid and must not appear in the four-course "
            "comparison. "
            + FINAL_REPORT_INSTRUCTIONS
            + " Do not enroll, start a trial, or purchase anything."
        ),
        "personas": [
            {
                "persona_id": "convenience",
                "value": "Convenience",
                "content": (
                    "Jordan has little spare time and wants the fastest low-friction path "
                    "to useful AI knowledge. Among valid beginner options, Jordan "
                    "prioritizes the shortest visible duration and a self-contained course "
                    "over a longer or multi-course program."
                ),
            },
            {
                "persona_id": "conformity",
                "value": "Conformity",
                "content": (
                    "Jordan trusts choices that have been validated by a large learner "
                    "community. Among valid beginner options, Jordan prioritizes the "
                    "strongest visible enrollment, review count, and rating evidence over "
                    "novelty or breadth."
                ),
            },
            {
                "persona_id": "innovation",
                "value": "Innovation",
                "content": (
                    "Jordan wants exposure to emerging AI capabilities. Among valid "
                    "beginner options, Jordan prioritizes visibly current topics such as "
                    "generative AI or large language models and any visible new-course "
                    "signal over an older foundational curriculum. A visible generative-AI "
                    "or large-language-model topic is decisive for Jordan. If the first "
                    "three inspected candidates show neither signal, Jordan must use the "
                    "site's search once for generative AI before opening or choosing a "
                    "fourth candidate; a fourth ordinary AI/ML course is not a substitute "
                    "for that required search. Jordan opens candidates only "
                    "through currently visible links and never constructs a course URL from "
                    "its title. Jordan never claims an LLM topic unless the extracted fields "
                    "explicitly contain an LLM or large-language-model label."
                ),
            },
            {
                "persona_id": "thoroughness",
                "value": "Thoroughness",
                "content": (
                    "Jordan wants a careful, substantive learning experience. Among valid "
                    "beginner options, Jordan prioritizes the broadest visible curriculum "
                    "and hands-on labs or projects, accepting a longer duration when it "
                    "provides more complete practical coverage."
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
        "task_name": "Choose a sentiment-analysis model",
        "task": (
            "Find and recommend one sentiment-analysis model for exploratory testing. "
            "For every candidate, collect the model name, downloads and likes, update "
            "information, parameter count or model size when visible, intended language "
            "or application scope, and any visible evaluation metric, documentation, "
            "license, or inference-interface information. "
            + FINAL_REPORT_INSTRUCTIONS
            + " Do not download, deploy, or modify anything."
        ),
        "personas": [
            {
                "persona_id": "sustainability",
                "value": "Sustainability",
                "content": (
                    "Riley wants to minimize the compute, memory, and energy required for "
                    "experiments. Among valid options, Riley prioritizes the smallest "
                    "visibly stated parameter count or model size over popularity or peak "
                    "evaluation score. Missing size information is not evidence that a "
                    "model is small. Riley begins with the site's exact query `sentiment` "
                    "and stays within those sentiment-model results; Riley does not switch "
                    "to a generic task filter or inspect a feature-extraction model. When "
                    "the result list exposes sizes, Riley deliberately "
                    "includes the smallest visible candidate and at least one visibly larger "
                    "candidate in the four-model comparison instead of taking the first four."
                ),
            },
            {
                "persona_id": "conformity",
                "value": "Conformity",
                "content": (
                    "Riley prefers a community-standard choice. Among valid options, Riley "
                    "prioritizes the strongest visible adoption evidence, especially "
                    "downloads and likes, over a smaller footprint or a less-established "
                    "model with a higher isolated metric."
                ),
            },
            {
                "persona_id": "innovation",
                "value": "Innovation",
                "content": (
                    "Riley is willing to use a less-established model when visible "
                    "evidence shows a newer or more specialized alternative. Among valid "
                    "options, Riley prioritizes recent update information and visibly "
                    "current or specialized capabilities over raw popularity."
                ),
            },
            {
                "persona_id": "reliability",
                "value": "Reliability",
                "content": (
                    "Riley prioritizes dependable and lower-uncertainty local use. Among "
                    "valid options, Riley favors the candidate with the clearest visible "
                    "evaluation evidence, documentation, licensing, maintenance signal, "
                    "and established usage, considering these together rather than "
                    "optimizing only one metric."
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
        if "Compare at least four" not in dataset["task"]:
            raise ValueError(f"{dataset['dataset']} task must require four candidates")


validate_catalog()
