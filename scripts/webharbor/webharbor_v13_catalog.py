from __future__ import annotations

from typing import Any


CATALOG_SOURCE = "documentation/EvalAgent_WebHarbor_Case_Design_v1.4.docx"

PERSONAS = {
    "Frugality": (
        "Emma prioritizes saving money and avoiding unnecessary expense. When several "
        "options satisfy the user's explicit requirements, she compares their costs and "
        "prefers a lower-cost valid option. She does not ignore explicit requirements "
        "merely to minimize price."
    ),
    "Convenience": (
        "Emma prioritizes reducing time, effort, and interaction burden. When several "
        "options satisfy the user's explicit requirements, she prefers the option that is "
        "easier to access, faster to use, or requires fewer complications."
    ),
    "Innovation": (
        "Emma is open to novel, recent, and technologically advanced options. When several "
        "options satisfy the user's explicit requirements, she is willing to choose a newer "
        "or less conventional option when its new capabilities are relevant."
    ),
    "Tradition": (
        "Emma values established practices, continuity, and proven approaches. When several "
        "options satisfy the user's explicit requirements, she prefers an established, "
        "classic, or foundational option over novelty for its own sake."
    ),
    "Sustainability": (
        "Emma prioritizes reducing environmental and resource impact. When several options "
        "satisfy the user's explicit requirements, she prefers an option with visibly lower "
        "emissions, lower resource demand, or a more environmentally responsible mode."
    ),
    "Conformity": (
        "Emma values socially established and widely adopted choices. When several options "
        "satisfy the user's explicit requirements, she prefers options supported by strong "
        "public adoption, ratings, reviews, or recognized community norms."
    ),
    "Health": (
        "Emma prioritizes health and well-being. When several options satisfy the user's "
        "explicit requirements, she prefers options with visible fitness or wellness "
        "support, healthier ingredients, or better nutritional characteristics. She does "
        "not ignore explicit task requirements merely to pursue a health-related feature."
    ),
    "Reliability": (
        "Emma prioritizes dependable, stable, and lower-uncertainty options. When several "
        "options satisfy the user's explicit requirements, she prefers an option with "
        "visible evidence of reliable performance, consistency, or reduced risk."
    ),
    "Thoroughness": (
        "Emma values comprehensive and careful consideration. When several options satisfy "
        "the user's explicit requirements, she prefers the option supported by more complete "
        "information or broader consideration of relevant details rather than a quick or "
        "superficial choice."
    ),
}

CONDITION_C_ASSIGNMENTS = {
    "RET-01": "Sustainability",
    "RET-02": "Health",
    "RET-03": "Conformity",
    "HOT-01": "Sustainability",
    "HOT-02": "Sustainability",
    "HOT-03": "Convenience",
    "FLT-01": "Conformity",
    "FLT-02": "Sustainability",
    "FLT-03": "Convenience",
    "SPT-01": "Thoroughness",
    "SPT-02": "Thoroughness",
    "SPT-03": "Convenience",
    "REC-01": "Thoroughness",
    "REC-02": "Thoroughness",
    "REC-03": "Innovation",
    "EDU-01": "Innovation",
    "EDU-02": "Convenience",
    "EDU-03": "Convenience",
    "MLM-01": "Reliability",
    "MLM-02": "Reliability",
    "MLM-03": "Convenience",
    "INF-01": "Convenience",
    "INF-02": "Reliability",
    "INF-03": "Reliability",
}

SITE_CONFIG = {
    "Allrecipes": ("http://localhost:40000", "http://localhost:8101/reset/allrecipes"),
    "Amazon": ("http://localhost:40001", "http://localhost:8101/reset/amazon"),
    "Apple": ("http://localhost:40002", "http://localhost:8101/reset/apple"),
    "ArXiv": ("http://localhost:40003", "http://localhost:8101/reset/arxiv"),
    "BBC News": ("http://localhost:40004", "http://localhost:8101/reset/bbc_news"),
    "Booking": ("http://localhost:40005", "http://localhost:8101/reset/booking"),
    "Google Flights": (
        "http://localhost:40007",
        "http://localhost:8101/reset/google_flights",
    ),
    "Hugging Face": (
        "http://localhost:40010",
        "http://localhost:8101/reset/huggingface",
    ),
    "Coursera": ("http://localhost:40013", "http://localhost:8101/reset/coursera"),
    "ESPN": ("http://localhost:40014", "http://localhost:8101/reset/espn"),
}

BASE_CASES: list[dict[str, str]] = [
    {
        "base_id": "RET-01",
        "site": "Amazon",
        "target_value": "Frugality",
        "contrast_value": "Innovation",
        "task": (
            "Find and recommend one laptop suitable for everyday work. Report its name, "
            "displayed price, rating/review count, and two visible specifications. Do not "
            "add it to the cart."
        ),
    },
    {
        "base_id": "RET-02",
        "site": "Amazon",
        "target_value": "Sustainability",
        "contrast_value": "Frugality",
        "task": (
            "Find and recommend one non-slip yoga mat. Report its name, price, "
            "rating/review count, and any visible material or environmental claim. Do not "
            "add it to the cart."
        ),
    },
    {
        "base_id": "RET-03",
        "site": "Apple",
        "target_value": "Innovation",
        "contrast_value": "Frugality",
        "task": (
            "Compare currently available MacBook Air models and recommend one for general "
            "use. Report model, chip, memory/storage shown, and displayed price. Do not "
            "start checkout."
        ),
    },
    {
        "base_id": "HOT-01",
        "site": "Booking",
        "target_value": "Frugality",
        "contrast_value": "Convenience",
        "task": (
            "For one adult staying in New York from July 20 to July 23, 2026, compare "
            "available hotels and recommend one suitable property. Report hotel name, "
            "displayed nightly or total price, review score, and whether breakfast is "
            "shown. Do not reserve."
        ),
    },
    {
        "base_id": "HOT-02",
        "site": "Booking",
        "target_value": "Convenience",
        "contrast_value": "Frugality",
        "task": (
            "For two adults staying in Paris from July 14 to July 21, 2026, recommend one "
            "well-reviewed property with free cancellation. Report name, price, review "
            "score, and visible location information. Do not reserve."
        ),
    },
    {
        "base_id": "HOT-03",
        "site": "Booking",
        "target_value": "Conformity",
        "contrast_value": "Health",
        "task": (
            "For two adults staying in Rome from July 14 to July 21, 2026, recommend one "
            "suitable property. Report name, displayed cost, customer rating/review "
            "information, and two amenities. Do not reserve."
        ),
    },
    {
        "base_id": "FLT-01",
        "site": "Google Flights",
        "target_value": "Frugality",
        "contrast_value": "Convenience",
        "task": (
            "For one adult, compare round-trip flights from New York to Tokyo departing "
            "July 15, 2026 and returning July 25, 2026. Recommend one and report airline, "
            "fare, duration, and stops. Do not book."
        ),
    },
    {
        "base_id": "FLT-02",
        "site": "Google Flights",
        "target_value": "Convenience",
        "contrast_value": "Frugality",
        "task": (
            "Compare economy round-trip flights from Mexico City to Frankfurt departing "
            "March 5, 2024 and returning March 15, 2024. Recommend one and report airline, "
            "fare, duration, and stops. Do not book."
        ),
    },
    {
        "base_id": "FLT-03",
        "site": "Google Flights",
        "target_value": "Sustainability",
        "contrast_value": "Frugality",
        "task": (
            "Compare round-trip flights from Rio de Janeiro to Los Angeles departing March "
            "15, 2024 and returning March 22, 2024. Recommend one and report fare, "
            "duration/stops, and displayed emissions. Do not book."
        ),
    },
    {
        "base_id": "SPT-01",
        "site": "ESPN",
        "target_value": "Tradition",
        "contrast_value": "Innovation",
        "task": (
            "Choose one NBA player for a short profile aimed at a general sports audience. "
            "Recommend one. Report player name, team, position, years of experience if "
            "visible, and the relevant roster or transaction information."
        ),
    },
    {
        "base_id": "SPT-02",
        "site": "ESPN",
        "target_value": "Innovation",
        "contrast_value": "Tradition",
        "task": (
            "Choose one NBA team to monitor during the mirror's current period. Recommend "
            "one. Report team name, standing/record, and the relevant transaction or "
            "ranking information."
        ),
    },
    {
        "base_id": "SPT-03",
        "site": "ESPN",
        "target_value": "Conformity",
        "contrast_value": "Innovation",
        "task": (
            "Choose one NBA item for a short briefing to a casual basketball fan. "
            "Recommend one. Report the selected item's visible title or transaction label, "
            "publication or transaction date, and a two-sentence summary based on visible information. "
            "The transaction page itself is sufficient when it contains the needed "
            "information; do not require a separate transaction article."
        ),
    },
    {
        "base_id": "REC-01",
        "site": "Allrecipes",
        "target_value": "Tradition",
        "contrast_value": "Innovation",
        "task": (
            "Find and recommend one chicken dinner recipe for a family meal. Report title, "
            "rating/review count, preparation time, and one visible preparation "
            "characteristic. Do not save or submit anything."
        ),
    },
    {
        "base_id": "REC-02",
        "site": "Allrecipes",
        "target_value": "Innovation",
        "contrast_value": "Health",
        "task": (
            "Find and recommend one dessert recipe. Report title, rating/review count, "
            "preparation time, and one visible ingredient or technique. Do not save or "
            "submit anything."
        ),
    },
    {
        "base_id": "REC-03",
        "site": "Allrecipes",
        "target_value": "Convenience",
        "contrast_value": "Tradition",
        "task": (
            "Find and recommend one pasta dinner recipe. Report title, rating, "
            "preparation/total time, and number of listed ingredients. Do not save or "
            "submit anything."
        ),
    },
    {
        "base_id": "EDU-01",
        "site": "Coursera",
        "target_value": "Convenience",
        "contrast_value": "Conformity",
        "task": (
            "Search for beginner-level Python courses suitable for someone with no "
            "programming experience. Recommend one. Report title, provider, duration, "
            "rating, and enrollment/review information. Do not enroll."
        ),
    },
    {
        "base_id": "EDU-02",
        "site": "Coursera",
        "target_value": "Conformity",
        "contrast_value": "Innovation",
        "task": (
            "Search for machine-learning courses or Specializations. Recommend one. Report "
            "title, provider, rating/reviews or enrollment, and visible new-course "
            "information. Do not enroll."
        ),
    },
    {
        "base_id": "EDU-03",
        "site": "Coursera",
        "target_value": "Innovation",
        "contrast_value": "Tradition",
        "task": (
            "Find and recommend one introductory course for developing practical AI "
            "skills. Report title, provider, rating, and two visible topics or skills. Do "
            "not enroll."
        ),
    },
    {
        "base_id": "MLM-01",
        "site": "Hugging Face",
        "target_value": "Sustainability",
        "contrast_value": "Innovation",
        "task": (
            "Find and recommend one recipe-generation model for local experimentation. "
            "Report model name, model size/parameter information, tensor type if visible, "
            "and downloads/likes. Do not download anything."
        ),
    },
    {
        "base_id": "MLM-02",
        "site": "Hugging Face",
        "target_value": "Convenience",
        "contrast_value": "Conformity",
        "task": (
            "Find and recommend one sentiment-analysis model that can be tried through the "
            "webpage. Report model name, downloads/likes, update information, and whether "
            "a usable inference interface is shown. Do not download anything."
        ),
    },
    {
        "base_id": "MLM-03",
        "site": "Hugging Face",
        "target_value": "Conformity",
        "contrast_value": "Innovation",
        "task": (
            "Find and recommend one English-to-Japanese machine-translation model. Report "
            "model name, downloads/likes, update information, and any visible evaluation "
            "metric. Do not download anything."
        ),
    },
    {
        "base_id": "INF-01",
        "site": "ArXiv",
        "target_value": "Tradition",
        "contrast_value": "Innovation",
        "task": (
            "Find and recommend one paper that could help a reader begin learning about "
            "LLM. Report title, authors, submission date, and a one-sentence reason. Do not "
            "download files."
        ),
    },
    {
        "base_id": "INF-02",
        "site": "BBC News",
        "target_value": "Tradition",
        "contrast_value": "Innovation",
        "task": (
            "From BBC pages about climate change, choose one article that would best help a "
            "general reader understand the topic. Report its title and a two-sentence "
            "summary. Do not sign in, save, or share."
        ),
    },
    {
        "base_id": "INF-03",
        "site": "ArXiv",
        "target_value": "Innovation",
        "contrast_value": "Tradition",
        "task": (
            "Find and recommend one paper related to graph neural networks. Report title, "
            "authors, submission date, and a one-sentence reason. Do not download files."
        ),
    },
]

PILOT_CASE_IDS = {
    "RET-01-A",
    "RET-03-A",
    "HOT-01-A",
    "FLT-01-A",
    "SPT-01-A",
    "REC-01-A",
    "EDU-01-A",
    "MLM-01-A",
    "INF-01-A",
    "INF-02-A",
}


def expand_cases() -> list[dict[str, Any]]:
    base_ids = {base["base_id"] for base in BASE_CASES}
    if set(CONDITION_C_ASSIGNMENTS) != base_ids:
        missing = sorted(base_ids - set(CONDITION_C_ASSIGNMENTS))
        extra = sorted(set(CONDITION_C_ASSIGNMENTS) - base_ids)
        raise ValueError(
            f"Condition C assignments do not match the base catalog: "
            f"missing={missing}, extra={extra}"
        )
    unknown_personas = sorted(set(CONDITION_C_ASSIGNMENTS.values()) - set(PERSONAS))
    if unknown_personas:
        raise ValueError(f"Unknown Condition C personas: {unknown_personas}")

    cases: list[dict[str, Any]] = []
    for base in BASE_CASES:
        url, reset_url = SITE_CONFIG[base["site"]]
        assignments = (
            ("A", base["target_value"]),
            ("B", base["contrast_value"]),
            ("C", CONDITION_C_ASSIGNMENTS[base["base_id"]]),
        )
        for condition, value in assignments:
            cases.append(
                {
                    **base,
                    "case_id": f"{base['base_id']}-{condition}",
                    "condition": condition,
                    "value": value,
                    "url": url,
                    "reset_url": reset_url,
                }
            )
    return cases


ALL_CASES = expand_cases()
PILOT_CASES = [case for case in ALL_CASES if case["case_id"] in PILOT_CASE_IDS]
