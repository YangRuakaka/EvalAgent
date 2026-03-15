"""
API routes for Agent as a Judge functionality.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import ValidationError

from ..schemas.judge import (
    ExperimentEvaluationRequest,
    ExperimentEvaluationResponse,
    ConditionResult,
    ExperimentCriterionResult,
    StepEvaluationDetail,
    EvidenceCitation,
    EvaluateStatus,
    ExperimentCriterion,
    ConditionRequest,
    MultiConditionAssessment,
    ConditionComparison,
    CriteriaMultiConditionAssessment,
    RankingItem,
)
from ..schemas.browser_agent import BrowserAgentTask
from ..api.deps import get_judge_services, JudgeServices
from ..core.config import settings
from ..core.normalizers import normalize_run_index, normalize_to_string
from ..core.storage_paths import get_condition_lookup_dirs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/judge", tags=["judge"])


def _map_verdict_to_status(verdict: str) -> EvaluateStatus:
    normalized = str(verdict or "").strip().lower()
    if normalized in {"pass", "fail", "partial"}:
        return EvaluateStatus(normalized)
    return EvaluateStatus.UNKNOWN


def _coerce_overall_assessment_to_binary(status: EvaluateStatus) -> EvaluateStatus:
    if status == EvaluateStatus.PASS:
        return EvaluateStatus.PASS
    return EvaluateStatus.FAIL


def _clip_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _compute_step_confidence(
    ev_list: List[EvidenceCitation],
    fallback_confidence: float,
) -> float:
    base = _clip_confidence(fallback_confidence)
    if not ev_list:
        return _clip_confidence(base * 0.75)

    evidence_count = len(ev_list)
    source_diversity = len(
        {
            ev.source_field.value if hasattr(ev.source_field, "value") else str(ev.source_field)
            for ev in ev_list
        }
    )
    avg_reasoning_len = sum(len((ev.reasoning or "").strip()) for ev in ev_list) / evidence_count
    verdicts = {
        str(ev.verdict.value if hasattr(ev.verdict, "value") else ev.verdict).lower()
        for ev in ev_list
        if ev.verdict
    }

    count_score = min(1.0, evidence_count / 3.0)
    source_score = min(1.0, source_diversity / 3.0)
    reasoning_score = min(1.0, avg_reasoning_len / 120.0)
    consistency_score = 1.0 if len(verdicts) <= 1 else max(0.35, 1.0 - 0.25 * (len(verdicts) - 1))

    technical_score = (
        0.36 * base
        + 0.24 * count_score
        + 0.16 * source_score
        + 0.14 * reasoning_score
        + 0.10 * consistency_score
    )

    if evidence_count > 1 and len(verdicts) > 1:
        entropy = 0.0
        verdict_list = [
            str(ev.verdict.value if hasattr(ev.verdict, "value") else ev.verdict).lower()
            for ev in ev_list
            if ev.verdict
        ]
        if verdict_list:
            for verdict in set(verdict_list):
                probability = verdict_list.count(verdict) / len(verdict_list)
                entropy -= probability * math.log(max(probability, 1e-8))
            max_entropy = math.log(max(2, len(set(verdict_list))))
            if max_entropy > 0:
                technical_score *= max(0.7, 1.0 - 0.2 * (entropy / max_entropy))

    return _clip_confidence(technical_score)


def _synthesize_step_status(
    ev_list: List[EvidenceCitation],
    criterion_status: EvaluateStatus,
) -> EvaluateStatus:
    counts = {
        EvaluateStatus.PASS: 0,
        EvaluateStatus.FAIL: 0,
        EvaluateStatus.PARTIAL: 0,
    }

    for ev in ev_list:
        if ev.verdict in counts:
            counts[ev.verdict] += 1

    total_votes = sum(counts.values())
    if total_votes == 0:
        return criterion_status

    if counts[EvaluateStatus.PASS] > 0 and counts[EvaluateStatus.FAIL] > 0:
        evidence_status = EvaluateStatus.PARTIAL
    else:
        evidence_status = max(
            (EvaluateStatus.PASS, EvaluateStatus.FAIL, EvaluateStatus.PARTIAL),
            key=lambda status: counts[status],
        )

    if criterion_status == EvaluateStatus.UNKNOWN:
        return evidence_status
    if evidence_status == criterion_status:
        return evidence_status
    if evidence_status == EvaluateStatus.PARTIAL or criterion_status == EvaluateStatus.PARTIAL:
        return EvaluateStatus.PARTIAL
    if {evidence_status, criterion_status} == {EvaluateStatus.PASS, EvaluateStatus.FAIL}:
        return EvaluateStatus.PARTIAL
    return evidence_status


def _build_step_reasoning(
    ev_list: List[EvidenceCitation],
    criterion_status: EvaluateStatus,
    synthesized_status: EvaluateStatus,
    criterion_reasoning: str,
) -> str:
    reasoning_snippets = [
        (ev.reasoning or "").strip()
        for ev in ev_list
        if (ev.reasoning or "").strip()
    ]
    unique_snippets: List[str] = []
    for snippet in reasoning_snippets:
        if snippet not in unique_snippets:
            unique_snippets.append(snippet)

    source_count = len(
        {
            ev.source_field.value if hasattr(ev.source_field, "value") else str(ev.source_field)
            for ev in ev_list
        }
    )

    evidence_note = " ".join(unique_snippets[:2])
    if not evidence_note:
        evidence_note = "Evidence excerpts are used as primary support for this step."

    context_reasoning = (criterion_reasoning or "").strip()
    context_note = (
        f" Phase/criterion context: {context_reasoning[:180]}"
        if context_reasoning
        else ""
    )

    return (
        f"Step verdict synthesized from {len(ev_list)} evidence item(s) across {source_count} source field(s). "
        f"Evidence-backed status + phase/criterion context ({criterion_status.value}) -> {synthesized_status.value}. "
        f"{evidence_note}{context_note}"
    )


async def _process_single_criterion(
    crit: ExperimentCriterion,
    task: BrowserAgentTask,
    all_steps: List[dict],
    personas: List[str],
    models: List[str],
    services: JudgeServices,
    judge_model: Optional[str] = None,
    step_max_concurrency: Optional[int] = None,
    llm_semaphore: Optional[asyncio.Semaphore] = None,
) -> Optional[ExperimentCriterionResult]:
    """Process a single criterion evaluation asynchronously."""
    logger.info(f"Evaluating criterion: {crit.title}")

    # 5. Evaluate
    try:
        logger.info("Starting unified evaluation for criterion: %s", crit.title)
        eval_result = await services.judge_evaluator.evaluate_criterion_unified(
            criterion_name=crit.title,
            criterion_assertion=crit.assertion,
            task_name=task.name,
            personas=personas,
            models=models,
            all_steps=all_steps or [],
            model_name=judge_model,
            criterion_description=crit.description,
            step_max_concurrency=step_max_concurrency,
            llm_semaphore=llm_semaphore,
        )
        logger.info(f"Evaluation result: verdict={eval_result.verdict}, reasoning length={len(eval_result.reasoning) if eval_result.reasoning else 0}")
        
        # Map to response format
        logger.info(f"Mapping evaluation result. Verdict: {eval_result.verdict}, Relevant steps: {eval_result.relevant_steps}")

        normalized_overall_verdict = (
            EvaluateStatus(eval_result.verdict.lower())
            if eval_result.verdict.lower() in ["pass", "fail", "partial"]
            else EvaluateStatus.UNKNOWN
        )
        
        involved_steps_list = []
        
        # Only build involved_steps from grounded highlighted evidence.
        if eval_result.highlighted_evidence:
            # Group evidence by step_index
            steps_evidence = {}
            for evidence in eval_result.highlighted_evidence:
                # Ensure evidence is an object
                ev_obj = evidence
                if isinstance(evidence, dict):
                    ev_obj = EvidenceCitation(**evidence)

                # Skip empty evidence text to avoid empty highlight sections in frontend
                if not (ev_obj.highlighted_text or "").strip():
                    continue
                    
                step_idx = ev_obj.step_index
                if step_idx not in steps_evidence:
                    steps_evidence[step_idx] = []
                steps_evidence[step_idx].append(ev_obj)

            llm_step_assessments = await services.judge_evaluator.synthesize_step_assessments(
                task_name=task.name,
                criterion_name=crit.title,
                criterion_assertion=crit.assertion,
                criterion_description=crit.description or "",
                personas=personas,
                models=models,
                criterion_verdict=normalized_overall_verdict.value,
                criterion_reasoning=eval_result.reasoning or "",
                phase_criterion_summary=eval_result.aggregated_step_summary or "",
                evidence_by_step=steps_evidence,
                model_name=judge_model,
                llm_semaphore=llm_semaphore,
            )
            
            # Create a StepEvaluationDetail for each step with evidence
            for step_idx, ev_list in sorted(steps_evidence.items(), key=lambda item: item[0]):
                llm_assessment = llm_step_assessments.get(step_idx, {}) if isinstance(llm_step_assessments, dict) else {}
                llm_verdict = str(llm_assessment.get("verdict", "")).strip().lower()
                if llm_verdict in {"pass", "fail", "partial", "unknown"}:
                    step_verdict = EvaluateStatus(llm_verdict)
                else:
                    step_verdict = _synthesize_step_status(
                        ev_list=ev_list,
                        criterion_status=normalized_overall_verdict,
                    )

                llm_reasoning = str(llm_assessment.get("reasoning", "") or "").strip()
                if llm_reasoning:
                    step_reasoning = llm_reasoning
                else:
                    step_reasoning = _build_step_reasoning(
                        ev_list=ev_list,
                        criterion_status=normalized_overall_verdict,
                        synthesized_status=step_verdict,
                        criterion_reasoning=eval_result.reasoning,
                    )

                llm_confidence = llm_assessment.get("confidence_score")
                try:
                    fallback_confidence = float(llm_confidence)
                except Exception:
                    fallback_confidence = float(eval_result.confidence_score or 0.0)
                    
                # Convert evidence back to dicts
                ev_dicts = [ev.model_dump() for ev in ev_list]
                
                step_detail = StepEvaluationDetail(
                    evaluateStatus=step_verdict,
                    reasoning=step_reasoning,
                    highlighted_evidence=ev_dicts,
                    confidenceScore=_compute_step_confidence(
                        ev_list,
                        fallback_confidence,
                    ),
                    steps=[step_idx]
                )
                involved_steps_list.append(step_detail)

        if not involved_steps_list:
            raw_relevant_steps = [
                step_idx
                for step_idx in (eval_result.relevant_steps or [])
                if isinstance(step_idx, int)
            ]
            logger.warning(
                "No grounded highlighted evidence for criterion '%s'; skipping step-level verdict emission (raw_relevant_steps=%s)",
                crit.title,
                raw_relevant_steps,
            )
        
        logger.info(f"Created {len(involved_steps_list)} StepEvaluationDetail objects")
        
        overall_assessment = _coerce_overall_assessment_to_binary(
            _map_verdict_to_status(eval_result.verdict)
        )
        overall_reasoning = eval_result.reasoning or ""
        confidence = float(eval_result.confidence_score or 0.0)
        
        return ExperimentCriterionResult(
            title=crit.title,
            assertion=crit.assertion,
            description=crit.description,
            involved_steps=involved_steps_list,
            overall_assessment=overall_assessment,
            overall_reasoning=overall_reasoning,
            confidence=confidence
        )
        
    except Exception as e:
        logger.error(f"Evaluation failed for criterion {crit.title}: {e}")
        return ExperimentCriterionResult(
            title=crit.title,
            assertion=crit.assertion,
            description=crit.description,
            involved_steps=[],
            overall_assessment=EvaluateStatus.UNKNOWN,
            overall_reasoning=f"Criterion evaluation failed: {str(e)}",
            confidence=0.0,
        )


async def _load_condition_run_data(
    condition: ConditionRequest,
    history_lookup_dirs: List[Path],
) -> Optional[Dict]:
    """Load run data for a condition from disk."""
    logger.info(f"Loading data for condition: {condition.conditionID}")

    requested_condition_id = normalize_to_string(condition.conditionID, "").strip()

    def _build_lookup_ids(raw_condition_id: str) -> List[str]:
        if not raw_condition_id:
            return []

        normalized_candidates: List[str] = []

        def _append(candidate: str) -> None:
            if not candidate:
                return
            if candidate not in normalized_candidates:
                normalized_candidates.append(candidate)

        base_name = raw_condition_id.replace("\\", "/").split("/")[-1].strip()
        while base_name.lower().endswith(".json"):
            base_name = base_name[:-5].strip()

        stripped_raw = raw_condition_id
        while stripped_raw.lower().endswith(".json"):
            stripped_raw = stripped_raw[:-5].strip()

        _append(base_name)
        _append(stripped_raw)
        return normalized_candidates

    lookup_ids = _build_lookup_ids(requested_condition_id)
    if not lookup_ids:
        logger.error("Empty conditionID in request, cannot load condition")
        return None
    
    # 1. Load run data using conditionID as filename
    try:
        json_file = None
        for lookup_dir in history_lookup_dirs:
            for lookup_id in lookup_ids:
                filename = f"{lookup_id}.json"
                candidate = lookup_dir / filename
                if candidate.exists() and candidate.is_file():
                    json_file = candidate
                    break
            if json_file is not None:
                break

        if json_file is None:
            logger.error(
                "Condition file not found for %s (normalized candidates=%s, searched dirs=%s)",
                requested_condition_id,
                lookup_ids,
                [path.as_posix() for path in history_lookup_dirs],
            )
            return None
        
        with open(json_file, 'r', encoding='utf-8') as f:
            run_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load condition {condition.conditionID}: {e}")
        return None
        
    metadata = run_data.get("metadata", {})
    details = run_data.get("details", {})
    all_steps = details.get("model_outputs", [])
    
    # Extract task from nested object or flat fields
    task_obj = metadata.get("task", {})
    if isinstance(task_obj, dict):
        task = BrowserAgentTask(
            name=task_obj.get("name", "Unknown Task"),
            description=task_obj.get("description", ""),
            url=task_obj.get("url", "")
        )
    else:
        task = BrowserAgentTask(
            name=metadata.get("task_name", "Unknown Task"),
            description=metadata.get("task_description", ""),
            url=metadata.get("task_url", "")
        )
    
    # Extract persona and model from metadata
    persona = normalize_to_string(metadata.get("persona", ""), "")
    personas = [persona] if persona else []
    
    value = normalize_to_string(metadata.get("value", ""), "")
    
    model = normalize_to_string(metadata.get("model", ""), "")
    models = [model] if model else []
    
    run_index = normalize_run_index(metadata.get("run_index", 1), requested_condition_id)

    logger.info(f"Loaded condition data: persona={persona}, value={value}, model={model}, run_index={run_index}, steps={len(all_steps)}")

    return {
        "conditionID": requested_condition_id,
        "task": task,
        "all_steps": all_steps,
        "personas": personas,
        "models": models,
        "run_index": run_index,
        "persona_str": persona,
        "value_str": value,
        "model_str": model
    }

async def _evaluate_condition_criterion_pair(
    context: Dict,
    criterion: ExperimentCriterion,
    services: JudgeServices,
    judge_model: Optional[str] = None,
    step_max_concurrency: Optional[int] = None,
    llm_semaphore: Optional[asyncio.Semaphore] = None,
) -> Tuple[str, Optional[ExperimentCriterionResult]]:
    """Evaluate a single criterion for a loaded condition context."""
    result = await _process_single_criterion(
        crit=criterion,
        task=context["task"],
        all_steps=context["all_steps"],
        personas=context["personas"],
        models=context["models"],
        services=services,
        judge_model=judge_model,
        step_max_concurrency=step_max_concurrency,
        llm_semaphore=llm_semaphore,
    )
    return context["conditionID"], result


def _safe_condition_result(ctx: Dict[str, Any], criteria_results: List[ExperimentCriterionResult]) -> Optional[ConditionResult]:
    try:
        return ConditionResult(
            conditionID=normalize_to_string(ctx.get("conditionID"), ""),
            persona=normalize_to_string(ctx.get("persona_str"), ""),
            value=normalize_to_string(ctx.get("value_str"), "") or None,
            model=normalize_to_string(ctx.get("model_str"), ""),
            run_index=normalize_run_index(ctx.get("run_index"), normalize_to_string(ctx.get("conditionID"), "")),
            criteria=criteria_results,
        )
    except ValidationError as exc:
        logger.error("ConditionResult validation failed for condition %s: %s", ctx.get("conditionID"), exc)
        return None


async def _gather_with_limit(
    coroutines: List[asyncio.Future],
    max_concurrency: int,
    timeout_seconds: int = 0,
) -> List[Any]:
    limit = max(1, int(max_concurrency or 1))
    semaphore = asyncio.Semaphore(limit)
    effective_timeout = max(0, int(timeout_seconds or 0))

    async def _run(coroutine: asyncio.Future) -> Any:
        async with semaphore:
            try:
                if effective_timeout > 0:
                    return await asyncio.wait_for(coroutine, timeout=effective_timeout)
                return await coroutine
            except asyncio.TimeoutError:
                logger.warning("A judge coroutine timed out after %ss", effective_timeout)
                return None
            except Exception as exc:
                logger.error("A judge coroutine failed: %s", exc)
                return None

    return await asyncio.gather(*[_run(coroutine) for coroutine in coroutines])

def _build_ranking_reasoning(
    criterion: ExperimentCriterion,
    ranking_items: List[RankingItem],
) -> str:
    if not ranking_items:
        return f"No valid condition results were available for criterion '{criterion.title}'."

    lines = [
        f"Ranking for '{criterion.title}' is determined by combining overall assessment with evidence strength.",
        "Confidence score is retained for reporting only and is not used as a ranking basis.",
    ]
    best_item = ranking_items[0]
    lines.append(
        f"Top condition: persona '{best_item.persona}' using model '{best_item.model}' run {best_item.run_index}, {best_item.summary}."
    )

    for item in ranking_items[1:]:
        lines.append(
            f"Compared condition: persona '{item.persona}' using model '{item.model}' run {item.run_index}, {item.summary}."
        )

    return " ".join(lines)


def _compute_evidence_strength(criterion_result: ExperimentCriterionResult) -> float:
    """
    Compute a normalized evidence strength score for ranking.

    This score captures how much grounded evidence supports the criterion result.
    Confidence is intentionally excluded from this score.
    """
    step_details = criterion_result.involved_steps or []
    if not step_details:
        return 0.0

    evidence_count = 0
    unique_step_indexes = set()
    unique_sources = set()
    reasoning_support_count = 0
    verdict_total = 0
    verdict_match = 0

    for step_detail in step_details:
        unique_step_indexes.update(int(step_idx) for step_idx in (step_detail.steps or []))
        if (step_detail.reasoning or "").strip():
            reasoning_support_count += 1

        for evidence in step_detail.highlighted_evidence or []:
            highlighted_text = (evidence.highlighted_text or "").strip()
            if not highlighted_text:
                continue

            evidence_count += 1
            unique_step_indexes.add(int(evidence.step_index))
            source_name = (
                evidence.source_field.value
                if hasattr(evidence.source_field, "value")
                else str(evidence.source_field)
            )
            if source_name:
                unique_sources.add(source_name)
            if (evidence.reasoning or "").strip():
                reasoning_support_count += 1

            if evidence.verdict is not None:
                verdict_total += 1
                if evidence.verdict == step_detail.evaluateStatus:
                    verdict_match += 1

    evidence_density = min(1.0, evidence_count / 8.0)
    step_coverage = min(1.0, len(unique_step_indexes) / 4.0)
    source_diversity = min(1.0, len(unique_sources) / 3.0)
    reasoning_support = min(
        1.0,
        reasoning_support_count / max(1, evidence_count + len(step_details)),
    )
    verdict_alignment = (
        verdict_match / verdict_total
        if verdict_total > 0
        else 0.6
    )

    score = (
        0.45 * evidence_density
        + 0.20 * step_coverage
        + 0.20 * source_diversity
        + 0.10 * reasoning_support
        + 0.05 * verdict_alignment
    )
    return _clip_confidence(score)


def _fallback_ranking(
    condition_evaluations: dict,
    results: List[ConditionResult]
) -> List[RankingItem]:
    """
    Deterministic ranking for multi-condition comparison.

    Priority: overall assessment (pass > partial > fail > unknown),
    then evidence strength score.
    """
    status_priority = {
        EvaluateStatus.PASS: 0,
        EvaluateStatus.PARTIAL: 1,
        EvaluateStatus.FAIL: 2,
        EvaluateStatus.UNKNOWN: 3
    }
    
    condition_map = {result.conditionID: result for result in results}
    
    # Sort conditions
    sorted_conditions = sorted(
        condition_evaluations.items(),
        key=lambda x: (
            status_priority.get(x[1].overall_assessment, 3),
            -_compute_evidence_strength(x[1]),
            str(x[0]),
        )
    )
    
    ranking_items = []
    for rank, (cond_id, crit_result) in enumerate(sorted_conditions, 1):
        result = condition_map[cond_id]
        evidence_strength = _compute_evidence_strength(crit_result)
        ranking_item = RankingItem(
            rank=rank,
            condition_id=cond_id,
            overall_assessment=crit_result.overall_assessment,
            confidence=crit_result.confidence or 0,
            summary=(
                f"assessed as {crit_result.overall_assessment.value} "
                f"with evidence score {evidence_strength:.2f}"
            ),
            persona=result.persona,
            value=result.value,
            model=result.model,
            run_index=result.run_index
        )
        ranking_items.append(ranking_item)
    
    return ranking_items


def _build_condition_summaries_for_llm_ranking(
    condition_evaluations: Dict[str, ExperimentCriterionResult],
    results: List[ConditionResult],
) -> List[Dict[str, Any]]:
    condition_map = {result.conditionID: result for result in results}
    summaries: List[Dict[str, Any]] = []

    for condition_id, criterion_result in sorted(condition_evaluations.items(), key=lambda item: str(item[0])):
        condition_result = condition_map.get(condition_id)
        if condition_result is None:
            continue

        step_details = criterion_result.involved_steps or []
        evidence_count = 0
        source_fields = set()
        for step_detail in step_details:
            for evidence in step_detail.highlighted_evidence or []:
                if not (evidence.highlighted_text or "").strip():
                    continue
                evidence_count += 1
                source_name = (
                    evidence.source_field.value
                    if hasattr(evidence.source_field, "value")
                    else str(evidence.source_field)
                )
                if source_name:
                    source_fields.add(source_name)

        summaries.append(
            {
                "condition_id": condition_id,
                "persona": condition_result.persona,
                "value": condition_result.value,
                "model": condition_result.model,
                "run_index": condition_result.run_index,
                "overall_assessment": (criterion_result.overall_assessment or EvaluateStatus.UNKNOWN).value,
                "overall_reasoning": criterion_result.overall_reasoning or "",
                "evidence_score_hint": _compute_evidence_strength(criterion_result),
                "evidence_item_count": evidence_count,
                "evidence_source_diversity": len(source_fields),
                "step_count": len(step_details),
                # Included for reporting context only; ranking prompt explicitly forbids using it.
                "confidence_for_reporting": float(criterion_result.confidence or 0.0),
            }
        )

    return summaries


def _build_ranking_items_from_llm_output(
    llm_ranking_payload: Dict[str, Any],
    condition_evaluations: Dict[str, ExperimentCriterionResult],
    results: List[ConditionResult],
) -> List[RankingItem]:
    deterministic_ranking = _fallback_ranking(condition_evaluations, results)
    raw_ranking = llm_ranking_payload.get("ranking", []) if isinstance(llm_ranking_payload, dict) else []
    if not isinstance(raw_ranking, list):
        return deterministic_ranking

    valid_condition_ids = set(condition_evaluations.keys())
    ordered_condition_ids: List[str] = []
    reasoning_by_condition: Dict[str, str] = {}
    for item in raw_ranking:
        if not isinstance(item, dict):
            continue

        condition_id = normalize_to_string(item.get("condition_id"), "").strip()
        if not condition_id or condition_id not in valid_condition_ids or condition_id in ordered_condition_ids:
            continue

        ordered_condition_ids.append(condition_id)
        reasoning_by_condition[condition_id] = normalize_to_string(item.get("reasoning"), "").strip()

    if not ordered_condition_ids:
        return deterministic_ranking

    # Ensure no condition is dropped if LLM output is incomplete.
    for fallback_item in deterministic_ranking:
        if fallback_item.condition_id not in ordered_condition_ids:
            ordered_condition_ids.append(fallback_item.condition_id)

    condition_map = {result.conditionID: result for result in results}
    ranking_items: List[RankingItem] = []
    for rank, condition_id in enumerate(ordered_condition_ids, 1):
        criterion_result = condition_evaluations.get(condition_id)
        condition_result = condition_map.get(condition_id)
        if criterion_result is None or condition_result is None:
            continue

        evidence_strength = _compute_evidence_strength(criterion_result)
        llm_reasoning = reasoning_by_condition.get(condition_id, "")
        summary = llm_reasoning or (
            f"assessed as {(criterion_result.overall_assessment or EvaluateStatus.UNKNOWN).value} "
            f"with evidence score {evidence_strength:.2f}"
        )
        ranking_items.append(
            RankingItem(
                rank=rank,
                condition_id=condition_id,
                overall_assessment=criterion_result.overall_assessment or EvaluateStatus.UNKNOWN,
                confidence=criterion_result.confidence or 0,
                summary=summary,
                persona=condition_result.persona,
                value=condition_result.value,
                model=condition_result.model,
                run_index=condition_result.run_index,
            )
        )

    return ranking_items or deterministic_ranking


async def _generate_multi_condition_assessment(
    results: List[ConditionResult],
    criteria: List[ExperimentCriterion],
    task_name: str,
    services: JudgeServices,
    judge_model: Optional[str] = None,
    llm_semaphore: Optional[asyncio.Semaphore] = None,
) -> Optional[MultiConditionAssessment]:
    """
    Generate multi-condition assessment comparing all conditions against each criterion.
    Uses LLM ranking based on overall assessment + evidence, with deterministic fallback.
    
    Args:
        results: List of evaluated conditions
        criteria: List of criteria that were evaluated
        
    Returns:
        MultiConditionAssessment if there are 2+ conditions, None otherwise
    """
    if len(results) < 2:
        return None
    
    criteria_comparisons = []
    
    for criterion in criteria:
        # Extract the corresponding criterion results from all conditions
        criterion_results = {}
        for result in results:
            # Find the matching criterion result
            matching_criterion = next(
                (c for c in result.criteria if c.title == criterion.title),
                None
            )
            if matching_criterion:
                criterion_results[result.conditionID] = matching_criterion
        
        if not criterion_results:
            continue

        llm_condition_summaries = _build_condition_summaries_for_llm_ranking(
            criterion_results,
            results,
        )
        llm_ranking_payload = await services.judge_evaluator.rank_multi_conditions(
            task_name=task_name,
            criterion_name=criterion.title,
            criterion_assertion=criterion.assertion,
            criterion_description=criterion.description or "",
            condition_summaries=llm_condition_summaries,
            model_name=judge_model,
            llm_semaphore=llm_semaphore,
        )

        ranking_items = _build_ranking_items_from_llm_output(
            llm_ranking_payload=llm_ranking_payload,
            condition_evaluations=criterion_results,
            results=results,
        )
        ranking_reasoning = normalize_to_string(
            llm_ranking_payload.get("ranking_reasoning") if isinstance(llm_ranking_payload, dict) else "",
            "",
        ).strip() or _build_ranking_reasoning(criterion, ranking_items)
        
        best_condition_id = ranking_items[0].condition_id if ranking_items else None
        if not best_condition_id:
            continue
        
        comparison_summary = normalize_to_string(
            llm_ranking_payload.get("comparison_summary") if isinstance(llm_ranking_payload, dict) else "",
            "",
        ).strip()
        if not comparison_summary:
            comparison_summary_parts = []
            for item in ranking_items:
                comparison_summary_parts.append(f"{item.condition_id}: {item.summary}")
            comparison_summary = " > ".join(comparison_summary_parts)
        
        condition_comparison = ConditionComparison(
            best_condition_id=best_condition_id,
            best_condition_rank=1,
            ranking=ranking_items,
            ranking_reasoning=ranking_reasoning,
            comparison_summary=comparison_summary
        )
        
        criteria_multi_condition_assessment = CriteriaMultiConditionAssessment(
            title=criterion.title,
            assertion=criterion.assertion,
            description=criterion.description,
            condition_comparison=condition_comparison
        )
        
        criteria_comparisons.append(criteria_multi_condition_assessment)
    
    return MultiConditionAssessment(
        criteria_comparisons=criteria_comparisons,
        total_conditions=len(results)
    )


@router.post("/evaluate-experiment", response_model=ExperimentEvaluationResponse)
async def evaluate_experiment(
    request: ExperimentEvaluationRequest,
    services: JudgeServices = Depends(get_judge_services)
) -> ExperimentEvaluationResponse:
    """
    Evaluate an experiment consisting of multiple conditions (runs) against a shared set of criteria.
    
    This endpoint handles the structure requested for the frontend experiments view.
    It orchestrates the evaluation process using a flattened concurrency model:
    1. Load run data for all conditions concurrently.
    2. Create M*N evaluation tasks (Conditions * Criteria).
    3. Execute all evaluation tasks concurrently.
    4. Aggregate results by condition.
    5. Evaluate multi-condition assessment if applicable.
    """
    max_concurrency = max(1, settings.JUDGE_EVALUATION_MAX_CONCURRENCY)
    configured_step_max_concurrency = max(1, int(getattr(settings, "JUDGE_EVALUATION_STEP_MAX_CONCURRENCY", 12) or 12))
    total_llm_concurrency_budget = max(
        1,
        int(
            getattr(
                settings,
                "JUDGE_EVALUATION_TOTAL_LLM_CONCURRENCY_BUDGET",
                configured_step_max_concurrency * max_concurrency,
            )
            or (configured_step_max_concurrency * max_concurrency)
        ),
    )
    step_max_concurrency = max(
        1,
        min(configured_step_max_concurrency, total_llm_concurrency_budget // max(1, max_concurrency)),
    )
    task_timeout_seconds = max(0, int(getattr(settings, "JUDGE_EVALUATION_TASK_TIMEOUT_SECONDS", 0) or 0))
    llm_semaphore = asyncio.Semaphore(total_llm_concurrency_budget)
    logger.info(
        "Received experiment evaluation request with %d conditions and %d criteria (judge_model=%s, max_concurrency=%d, step_max_concurrency=%d, llm_budget=%d, task_timeout_seconds=%d)",
        len(request.conditions),
        len(request.criteria),
        request.judge_model,
        max_concurrency,
        step_max_concurrency,
        total_llm_concurrency_budget,
        task_timeout_seconds,
    )
    logger.info(
        "Evaluate request conditionIDs=%s, criteria_titles=%s",
        [normalize_to_string(c.conditionID, "").strip() for c in request.conditions],
        [normalize_to_string(c.title, "").strip() for c in request.criteria],
    )

    if not request.conditions:
        raise HTTPException(status_code=400, detail={"message": "No conditions selected for evaluation."})
    if not request.criteria:
        raise HTTPException(status_code=400, detail={"message": "No criteria selected for evaluation."})
    
    history_lookup_dirs = get_condition_lookup_dirs(settings)
    
    # 1. Load data for all conditions concurrently
    load_tasks = []
    for condition in request.conditions:
        load_tasks.append(_load_condition_run_data(condition, history_lookup_dirs))
    
    loaded_contexts_raw = await _gather_with_limit(
        load_tasks,
        max_concurrency=max_concurrency,
        timeout_seconds=task_timeout_seconds,
    )
    loaded_contexts = [ctx for ctx in loaded_contexts_raw if ctx is not None]

    requested_condition_ids = [normalize_to_string(cond.conditionID, "").strip() for cond in request.conditions]
    loaded_condition_ids = {
        normalize_to_string(ctx.get("conditionID"), "").strip()
        for ctx in loaded_contexts
    }
    missing_condition_ids = [cond_id for cond_id in requested_condition_ids if cond_id and cond_id not in loaded_condition_ids]
    
    if not loaded_contexts:
        logger.warning("No valid conditions loaded")
        raise HTTPException(
            status_code=400,
            detail={
                "message": "No valid conditions could be loaded for evaluation.",
                "requested_condition_ids": requested_condition_ids,
                "hint": "Use conditionID as filename stem (without extension), or ensure corresponding .json exists in history lookup dirs.",
            },
        )

    if missing_condition_ids:
        logger.warning("Some conditions could not be loaded: %s", missing_condition_ids)
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Some selected conditions could not be loaded.",
                "missing_condition_ids": missing_condition_ids,
                "requested_condition_ids": requested_condition_ids,
                "loaded_condition_ids": sorted(loaded_condition_ids),
            },
        )

    # 2. Flattened Evaluation: Create tasks for all (Condition, Criterion) pairs
    evaluation_tasks = []
    for ctx in loaded_contexts:
        for crit in request.criteria:
            evaluation_tasks.append(
                _evaluate_condition_criterion_pair(
                    ctx,
                    crit,
                    services,
                    judge_model=request.judge_model,
                    step_max_concurrency=step_max_concurrency,
                    llm_semaphore=llm_semaphore,
                )
            )
            
    logger.info("Starting %d evaluation tasks with bounded concurrency=%d", len(evaluation_tasks), max_concurrency)
    
    # 3. Execute all evaluations concurrently
    flat_results = await _gather_with_limit(
        evaluation_tasks,
        max_concurrency=max_concurrency,
        timeout_seconds=task_timeout_seconds,
    )
    
    # 4. Group results by condition
    # Map: conditionID -> List[ExperimentCriterionResult]
    results_by_condition = {ctx["conditionID"]: [] for ctx in loaded_contexts}
    
    for item in flat_results:
        if not item:
            continue
        cond_id, result = item
        if result is not None:
            results_by_condition[cond_id].append(result)
            
    # 5. Build final ConditionResult objects
    condition_results = []

    def _criterion_identity(criterion: ExperimentCriterion) -> Tuple[str, str]:
        return (
            normalize_to_string(getattr(criterion, "title", ""), "").strip(),
            normalize_to_string(getattr(criterion, "assertion", ""), "").strip(),
        )

    for ctx in loaded_contexts:
        cond_id = ctx["conditionID"]
        
        # Maintain order of criteria as requested
        current_criteria_results = results_by_condition[cond_id]
        crit_map = {
            _criterion_identity(res): res
            for res in current_criteria_results
        }
        
        sorted_results = []
        for req_crit in request.criteria:
            criterion_key = _criterion_identity(req_crit)
            if criterion_key in crit_map:
                sorted_results.append(crit_map[criterion_key])
                continue

            logger.error(
                "Missing criterion result for condition=%s, criterion=%s",
                cond_id,
                criterion_key,
            )
            sorted_results.append(
                ExperimentCriterionResult(
                    title=req_crit.title,
                    assertion=req_crit.assertion,
                    description=req_crit.description,
                    involved_steps=[],
                    overall_assessment=EvaluateStatus.UNKNOWN,
                    overall_reasoning="No criterion result produced (internal timeout/failure).",
                    confidence=0.0,
                )
            )
        
        cr = _safe_condition_result(ctx, sorted_results)
        if cr is not None:
            condition_results.append(cr)
        else:
            logger.warning("Skipping invalid condition result: %s", cond_id)
    
    shared_task_names: List[str] = []
    for ctx in loaded_contexts:
        raw_task = ctx.get("task")
        task_name = normalize_to_string(getattr(raw_task, "name", ""), "").strip()
        if task_name and task_name not in shared_task_names:
            shared_task_names.append(task_name)

    ranking_task_name = " ; ".join(shared_task_names)
    if len(shared_task_names) > 1:
        logger.warning(
            "Multiple task names detected for one experiment request: %s",
            shared_task_names,
        )

    # 6. Generate multi-condition assessment if there are 2+ conditions
    multi_condition_assessment = await _generate_multi_condition_assessment(
        condition_results,
        request.criteria,
        task_name=ranking_task_name,
        services=services,
        judge_model=request.judge_model,
        llm_semaphore=llm_semaphore,
    )
    
    # Create response
    response = ExperimentEvaluationResponse(conditions=condition_results, multi_condition_assessment=multi_condition_assessment)
    
    logger.info(f"Experiment evaluation response sent with {len(condition_results)} conditions")
        
    return response
