"""Three new-domain pre-run cases for the CHI user-study extension.

Each dataset is one fixed task evaluated under four personas.  The task text,
model, website snapshot, and execution settings stay fixed within a dataset;
only the persona changes.
"""

from __future__ import annotations

from typing import Any


MIN_RUN_STEPS = 5
MAX_RUN_STEPS = 10


COMPARISON_INSTRUCTIONS = (
    "Compare exactly three task-valid candidates before choosing. To keep the "
    "trajectory concise, open exactly two candidates' detail pages through the "
    "visible interface, including the final recommendation; compare the third using "
    "only fields visibly available on its search-result or category card and mark its "
    "other fields unavailable. Base every comparison on visibly shown information and "
    "do not infer missing attributes. Treat the requested comparison dimensions as "
    "evidence, not as fixed priorities: the persona alone determines the trade-off. "
    "In the final answer, include a compact three-candidate comparison table and end "
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
        "task_name": "Choose a dessert for a dinner with 4–6 guests",
        "task": (
            "Find and recommend one dessert recipe for a dinner with 4–6 guests. "
            "For every candidate, record the title, rating and review count, total or "
            "preparation time, serving count, and one visible presentation, ingredient, "
            "or preparation detail. A recipe does not need to serve exactly 4–6 to be "
            "task-valid; treat serving count as trade-off evidence about scale, waste, or "
            "effort. If an image conflicts with the written description, record the "
            "mismatch instead of resolving it by inference. "
            + COMPARISON_INSTRUCTIONS
            + " Do not save, rate, review, or submit anything."
        ),
        "personas": [
            {
                "persona_id": "conformity",
                "value": "Conformity",
                "content": (
                    "Maya wants a dessert that will feel socially safe for a mixed group. "
                    "Among task-valid options, she prioritizes broad visible endorsement: "
                    "a strong rating supported by a large review count. She prefers that "
                    "evidence over speed, novelty, or a more dramatic presentation. On "
                    "the category page, she deliberately includes the candidate with the "
                    "largest visible review count in her three-way comparison rather than "
                    "sampling only the first cards."
                ),
            },
            {
                "persona_id": "convenience",
                "value": "Convenience",
                "content": (
                    "Maya has little time and energy before dinner. Among task-valid "
                    "options, she prioritizes the shortest visible total time and the "
                    "simplest visible preparation method, while using serving count to "
                    "avoid obviously excessive work. She accepts lower popularity or a "
                    "less distinctive result for an easier experience."
                ),
            },
            {
                "persona_id": "innovation",
                "value": "Innovation",
                "content": (
                    "Maya wants the dinner dessert to introduce something unfamiliar. "
                    "Among task-valid options, she prioritizes a visibly unusual "
                    "ingredient, flavor combination, shape, or preparation technique over "
                    "popularity and familiarity. She accepts some extra effort and weaker "
                    "social proof, but not a recipe whose visible scale makes it plainly "
                    "unsuitable for the dinner. She deliberately includes a visibly "
                    "nonstandard-shape, unusual-ingredient, or no-bake candidate instead "
                    "of comparing only conventional chocolate cups, brownies, and "
                    "parfaits. An image-description mismatch is uncertainty, not evidence "
                    "of innovation."
                ),
            },
            {
                "persona_id": "aesthetic_expression",
                "value": "Aesthetic Expression",
                "content": (
                    "Maya wants the dessert to create a visually memorable centerpiece. "
                    "Among task-valid options, she prioritizes the visible finished-dish "
                    "image and presentation details such as layering, shape, color, and "
                    "garnish. She accepts extra time or effort for stronger visual "
                    "expression and downgrades a candidate when its image contradicts its "
                    "description. She deliberately includes at least one candidate whose "
                    "category image visibly shows decorative frosting, multiple colors, "
                    "or an elaborate baked presentation rather than comparing only brown "
                    "mousse or cup desserts."
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
        "task_name": "Choose an introductory AI course for a first learning goal",
        "task": (
            "Find and recommend one introductory AI course for a learner choosing a "
            "first structured AI learning goal. A candidate is task-valid only if the "
            "visible page identifies it as beginner or introductory and explicitly "
            "focuses on AI or machine learning. For every candidate, record the title, "
            "provider, duration, rating plus review or enrollment evidence, and visible "
            "modules, outcomes, projects, emerging-topic signals, or social-impact focus. "
            + COMPARISON_INSTRUCTIONS
            + " Do not enroll, start a trial, or purchase anything."
        ),
        "personas": [
            {
                "persona_id": "convenience",
                "value": "Convenience",
                "content": (
                    "Jordan wants the fastest low-friction introduction to useful AI "
                    "knowledge. Among task-valid options, Jordan prioritizes the shortest "
                    "visible duration and a self-contained course over a specialization or "
                    "long curriculum, accepting less depth or prestige."
                ),
            },
            {
                "persona_id": "mastery",
                "value": "Mastery",
                "content": (
                    "Jordan wants a foundation that supports deep, sustained competence. "
                    "Among task-valid options, Jordan prioritizes the broadest visible "
                    "curriculum, multiple modules, and hands-on assignments or projects. "
                    "Jordan accepts a much longer duration when the visible learning "
                    "structure is more comprehensive and demanding."
                ),
            },
            {
                "persona_id": "innovation",
                "value": "Innovation",
                "content": (
                    "Jordan wants exposure to a visibly emerging direction in AI. Among "
                    "task-valid options, Jordan prioritizes current topics such as "
                    "generative AI, large language models, or other explicitly recent "
                    "developments over an older general curriculum. Lower popularity alone "
                    "is not evidence of innovation; the page must show the emerging topic "
                    "or recent-change signal."
                ),
            },
            {
                "persona_id": "benevolence",
                "value": "Benevolence",
                "content": (
                    "Jordan wants AI learning to contribute to other people's wellbeing. "
                    "Among task-valid options, Jordan prioritizes visible outcomes about "
                    "ethics, fairness, empathy, accessibility, bias, or beneficial social "
                    "impact. Jordan accepts extra time and lower popularity for a clearer "
                    "connection to broader social good."
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
        "task_name": "Choose a sentiment-analysis model for a prototype",
        "task": (
            "Find and recommend one sentiment-analysis model for a text prototype. "
            "A candidate is task-valid only when its visible page identifies a sentiment "
            "or emotion text-classification use. For every candidate, record the exact "
            "model name, intended domain or language, parameter count, downloads and "
            "likes, update date, sentiment classes or ambiguity-handling capability, and "
            "one visible evaluation, documentation, license, or inference signal. Begin "
            "with the exact site search `sentiment analysis`. "
            + COMPARISON_INSTRUCTIONS
            + " Do not download, deploy, run inference, or modify anything."
        ),
        "personas": [
            {
                "persona_id": "sustainability",
                "value": "Sustainability",
                "content": (
                    "Riley wants to minimize compute, memory, and energy use. Among "
                    "task-valid, domain-appropriate options, Riley prioritizes the smallest "
                    "visibly stated parameter count. Missing size information is not "
                    "evidence that a model is small, and a small model specialized for the "
                    "wrong domain should not be treated as sufficient. Riley accepts lower "
                    "popularity or peak metrics for a lighter adequate option."
                ),
            },
            {
                "persona_id": "conformity",
                "value": "Conformity",
                "content": (
                    "Riley prefers a community-standard model. Among task-valid options, "
                    "Riley prioritizes the strongest combined visible adoption evidence "
                    "from downloads and likes over smaller size, newer updates, or unusual "
                    "capabilities. If downloads and likes point to different candidates, "
                    "Riley must state that conflict instead of claiming one leads both."
                ),
            },
            {
                "persona_id": "innovation",
                "value": "Innovation",
                "content": (
                    "Riley wants to explore a recent or distinctive sentiment capability. "
                    "Among task-valid options, Riley prioritizes a visibly recent update "
                    "and explicit current capability, such as newer-corpus training or "
                    "sarcasm handling, over raw popularity and model size. Riley accepts "
                    "greater uncertainty for that visibly supported novelty."
                ),
            },
            {
                "persona_id": "nuance",
                "value": "Nuance",
                "content": (
                    "Riley wants the prototype to preserve distinctions that a binary label "
                    "would flatten. Among task-valid options, Riley prioritizes explicitly "
                    "visible multi-class sentiment, emotion categories, neutral handling, "
                    "or ambiguity-aware capabilities. Riley accepts lower adoption or a "
                    "less conventional model, but does not infer nuance from the model name "
                    "alone."
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
        if "Compare exactly three" not in dataset["task"]:
            raise ValueError(f"{dataset['dataset']} task must require three candidates")
        if "open exactly two candidates' detail pages" not in dataset["task"]:
            raise ValueError(f"{dataset['dataset']} task must require detail-page evidence")


validate_catalog()
