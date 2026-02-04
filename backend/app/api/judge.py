"""
API routes for Agent as a Judge functionality.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any

from fastapi import APIRouter, HTTPException, Depends
from langchain_core.messages import HumanMessage

from ..schemas.judge import (
    GranularityAnalysisRequest,
    GranularityRequirementResponse,
    TaskDecompositionRequest,
    StepAggregationRequest,
    TaskDecomposition,
    AggregatedSteps,
    ExperimentEvaluationRequest,
    ExperimentEvaluationResponse,
    ConditionResult,
    ExperimentCriterionResult,
    StepEvaluationDetail,
    EvidenceCitation,
    AgentStepField,
    EvaluateStatus,
    Granularity,
    ExperimentCriterion,
    ConditionRequest,
    MultiConditionAssessment,
    ConditionComparison,
    CriteriaMultiConditionAssessment,
    RankingItem,
)
from ..schemas.browser_agent import BrowserAgentTask
from ..api.deps import get_judge_services, JudgeServices
from ..services.history_logs_reader import HistoryLogsReader
from ..services.llm_factory import get_chat_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/judge", tags=["judge"])


@router.post("/analyze-granularity", response_model=GranularityRequirementResponse)
async def analyze_granularity(
    request: GranularityAnalysisRequest,
    services: JudgeServices = Depends(get_judge_services)
) -> GranularityRequirementResponse:
    """
    Analyze the granularity level needed for a specific criterion.
    
    Args:
        request: GranularityAnalysisRequest with criterion details
        services: Injected JudgeServices
        
    Returns:
        GranularityRequirementResponse with recommended granularity and rationale
    """
    
    logger.info(f"Analyzing granularity for criterion: {request.criterion.get('name')}")
    
    try:
        requirement = services.granularity_analyzer.analyze_criterion_granularity(
            criterion_name=request.criterion.get("name", "unknown"),
            criterion_assertion=request.criterion.get("assertion", ""),
            task_name=request.task_name
        )
        
        return GranularityRequirementResponse(
            criterion_name=requirement.criterion_name,
            required_granularity=requirement.required_granularity,
            rationale=requirement.rationale
        )
    except Exception as e:
        logger.error(f"Granularity analysis failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@router.post("/decompose-task", response_model=TaskDecomposition)
async def decompose_task(
    request: TaskDecompositionRequest,
    services: JudgeServices = Depends(get_judge_services)
) -> TaskDecomposition:
    """
    Decompose a task execution into semantic step clusters.
    
    Args:
        request: TaskDecompositionRequest with run_id
        services: Injected JudgeServices
        
    Returns:
        TaskDecomposition with semantic clusters and their definitions
    """
    
    logger.info(f"Task decomposition request for run: {request.run_id}")
    
    # Load the run result
    history_reader = HistoryLogsReader()
    try:
        run_data = history_reader.read_run(request.run_id)
    except Exception as e:
        logger.error(f"Failed to load run {request.run_id}: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Run {request.run_id} not found"
        )
    
    metadata = run_data.get("metadata", {})
    details = run_data.get("details", {})
    
    # Reconstruct task
    task = BrowserAgentTask(
        name=metadata.get("task_name", "Unknown Task"),
        description=metadata.get("task_description", ""),
        url=metadata.get("task_url", "")
    )
    
    # Extract steps
    all_steps = details.get("model_outputs", [])
    
    try:
        decomposition = services.task_decomposer.decompose_execution_steps(
            task=task,
            all_steps=all_steps,
            run_metadata={"run_id": request.run_id}
        )
        return decomposition
    except Exception as e:
        logger.error(f"Task decomposition failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Decomposition failed: {str(e)}"
        )


@router.post("/aggregate-steps", response_model=AggregatedSteps)
async def aggregate_steps(
    request: StepAggregationRequest,
    services: JudgeServices = Depends(get_judge_services)
) -> AggregatedSteps:
    """
    Aggregate steps at a specific granularity level.
    
    Useful for debugging and understanding how steps are being encoded at different granularities.
    
    Args:
        request: StepAggregationRequest with run_id and target granularity
        services: Injected JudgeServices
        
    Returns:
        AggregatedSteps with encoded/summarized content
    """
    
    logger.info(f"Step aggregation request for run: {request.run_id} at {request.granularity}")
    
    # Load the run result
    history_reader = HistoryLogsReader()
    try:
        run_data = history_reader.read_run(request.run_id)
    except Exception as e:
        logger.error(f"Failed to load run {request.run_id}: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Run {request.run_id} not found"
        )
    
    metadata = run_data.get("metadata", {})
    details = run_data.get("details", {})
    summary = run_data.get("summary", {})
    
    # Reconstruct task
    task = BrowserAgentTask(
        name=metadata.get("task_name", "Unknown Task"),
        description=metadata.get("task_description", ""),
        url=metadata.get("task_url", "")
    )
    
    # Extract steps
    all_steps = details.get("model_outputs", [])
    
    try:
        # Get task decomposition if needed
        task_decomposition = None
        if request.granularity in ["phase_level", "global_summary"]:
            task_decomposition = services.task_decomposer.decompose_execution_steps(
                task=task,
                all_steps=all_steps,
                run_metadata={"run_id": request.run_id}
            )
        
        execution_outcome = summary.get("task_result", "Task completed")
        
        aggregated = services.step_aggregator.aggregate_steps(
            all_steps=all_steps,
            granularity=request.granularity,
            task_decomposition=task_decomposition,
            task_name=task.name,
            execution_outcome=execution_outcome
        )
        return aggregated
    except Exception as e:
        logger.error(f"Step aggregation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Aggregation failed: {str(e)}"
        )


async def _generate_overall_assessment(
    criterion_title: str,
    criterion_assertion: str,
    criterion_description: str,
    task_name: str,
    granularity: Granularity,
    personas: List[str],
    models: List[str],
    eval_result,
    involved_steps: List[StepEvaluationDetail],
    services: JudgeServices
) -> tuple:
    """Generate overall assessment for a criterion using LLM.
    
    Args:
        criterion_title: Title of the criterion
        criterion_assertion: Assertion to verify
        criterion_description: Description of the criterion
        task_name: Name of the task
        granularity: Granularity level used
        personas: List of personas
        models: List of models
        eval_result: The evaluation result from judge evaluator
        involved_steps: List of step evaluation details
        services: Judge services instance
        
    Returns:
        Tuple of (overall_assessment, overall_reasoning, confidence)
    """
    try:
        from ..services.evaluation_prompts import EvaluationPrompts
        from langchain_core.prompts import PromptTemplate
        
        # Build evaluation details summary
        evaluation_details = "DETAILED EVALUATION RESULTS:\n"
        for i, step_detail in enumerate(involved_steps):
            evaluation_details += f"\nEvaluation {i+1}:\n"
            evaluation_details += f"  Status: {step_detail.evaluateStatus.value}\n"
            evaluation_details += f"  Reasoning: {step_detail.reasoning}\n"
            evaluation_details += f"  Confidence Score: {step_detail.confidenceScore}\n"
            evaluation_details += f"  Steps Involved: {step_detail.steps}\n"
            if step_detail.highlighted_evidence:
                evaluation_details += f"  Evidence Count: {len(step_detail.highlighted_evidence)}\n"
        
        # Build involved steps summary
        involved_steps_summary = "INVOLVED STEPS SUMMARY:\n"
        for step_detail in involved_steps:
            involved_steps_summary += f"- Steps {step_detail.steps}: {step_detail.evaluateStatus.value} ({step_detail.reasoning[:100]}...)\n"
        
        # Get the prompt template
        prompt_template = EvaluationPrompts.get_overall_criterion_assessment_prompt()
        
        # Format personas and models
        personas_str = ", ".join(personas) if personas else "None"
        models_str = ", ".join(models) if models else "None"
        
        # Prepare input for LLM
        input_dict = {
            "criterion_title": criterion_title,
            "criterion_assertion": criterion_assertion,
            "criterion_description": criterion_description,
            "task_name": task_name,
            "granularity": granularity.value,
            "personas": personas_str,
            "models": models_str,
            "evaluation_details": evaluation_details,
            "involved_steps_summary": involved_steps_summary
        }
        
        # Get LLM and create chain - use gpt-4o-mini for faster overall assessment generation
        llm = services.llm_factory.get_langchain_llm("gpt-4o-mini")
        chain = prompt_template | llm
        
        # Log the prompt
        formatted_prompt = prompt_template.format(**input_dict)
        logger.info(f"Overall assessment prompt for '{criterion_title}':\n{formatted_prompt}")
        print("\n" + "="*80)
        print(f"[OVERALL ASSESSMENT PROMPT] for criterion '{criterion_title}'")
        print("="*80)
        print(formatted_prompt)
        print("="*80)
        
        # Invoke LLM
        response = chain.invoke(input_dict)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        logger.info(f"Overall assessment response:\n{response_text}")
        print("[OVERALL ASSESSMENT RESPONSE]:")
        print(response_text)
        print("="*80 + "\n")
        
        # Parse response
        try:
            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("Could not find JSON in overall assessment response")
                return EvaluateStatus.UNKNOWN, "Failed to parse LLM response", 0.0
            
            json_str = response_text[json_start:json_end]
            response_data = json.loads(json_str)
            
            overall_assessment = response_data.get("overall_assessment", "partial").lower()
            # Convert to EvaluateStatus enum
            if overall_assessment in ["pass", "fail", "partial"]:
                overall_assessment = EvaluateStatus(overall_assessment)
            else:
                overall_assessment = EvaluateStatus.UNKNOWN
            
            overall_reasoning = response_data.get("overall_reasoning", "")
            confidence = float(response_data.get("confidence_score", 0.5))
            
            logger.info(f"Parsed overall assessment: {overall_assessment}, reasoning: {overall_reasoning[:100]}..., confidence: {confidence}")
            return overall_assessment, overall_reasoning, confidence
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse overall assessment JSON: {e}")
            return EvaluateStatus.UNKNOWN, f"Response parsing error: {str(e)}", 0.0
        
    except Exception as e:
        logger.error(f"Overall assessment generation failed: {e}")
        return EvaluateStatus.UNKNOWN, f"Assessment generation failed: {str(e)}", 0.0


async def _process_single_criterion(
    crit: ExperimentCriterion,
    task: BrowserAgentTask,
    all_steps: List[dict],
    personas: List[str],
    models: List[str],
    services: JudgeServices
) -> Optional[ExperimentCriterionResult]:
    """Process a single criterion evaluation asynchronously."""
    logger.info(f"Evaluating criterion: {crit.title}")
    
    # 2. Analyze granularity
    try:
        # Allow STEP_LEVEL, PHASE_LEVEL, and GLOBAL_SUMMARY
        granularity_req = services.granularity_analyzer.analyze_criterion_granularity(
            criterion_name=crit.title,
            criterion_assertion=crit.assertion,
            task_name=task.name,
            allowed_granularities=[Granularity.STEP_LEVEL, Granularity.PHASE_LEVEL, Granularity.GLOBAL_SUMMARY]
        )
        target_granularity = granularity_req.required_granularity
        logger.info(f"Determined granularity for criterion '{crit.title}': {target_granularity}")
    except Exception as e:
        logger.error(f"Granularity analysis failed: {e}")
        target_granularity = Granularity.GLOBAL_SUMMARY # Fallback
    
    # 3. Decompose task (if needed)
    decomposition = None
    # Only decompose if PHASE_LEVEL granularity is required
    if target_granularity == Granularity.PHASE_LEVEL:
        try:
            decomposition = services.task_decomposer.decompose_for_phase_evaluation(
                task=task,
                all_steps=all_steps,
                criterion_title=crit.title,
                criterion_assertion=crit.assertion
            )
            if decomposition is None:
                logger.warning("Phase decomposition returned None, falling back to STEP_LEVEL")
                target_granularity = Granularity.STEP_LEVEL
        except Exception as e:
            logger.error(f"Phase decomposition failed: {e}", exc_info=True)
            target_granularity = Granularity.STEP_LEVEL
    
    # 4. Aggregate steps
    try:
        logger.info(f"Starting step aggregation. All steps count: {len(all_steps)}, Granularity: {target_granularity}")
        aggregated_steps = services.step_aggregator.aggregate_steps(
            all_steps=all_steps,
            granularity=target_granularity,
            task_decomposition=decomposition,
            task_name=task.name
        )
        logger.info(f"Step aggregation successful. Aggregated steps type: {type(aggregated_steps)}")
    except Exception as e:
        logger.error(f"Aggregation failed: {e}", exc_info=True)
        return None

    # 5. Evaluate
    try:
        logger.info(f"Starting evaluation for criterion: {crit.title}")
        eval_result = await services.judge_evaluator.evaluate_criterion(
            criterion_name=crit.title,
            criterion_assertion=crit.assertion,
            aggregated_steps=aggregated_steps,
            task_name=task.name,
            personas=personas,
            models=models,
            all_steps=all_steps,
            criterion_description=crit.description
        )
        logger.info(f"Evaluation result: verdict={eval_result.verdict}, reasoning length={len(eval_result.reasoning) if eval_result.reasoning else 0}")
        
        # Map to response format
        logger.info(f"Mapping evaluation result. Verdict: {eval_result.verdict}, Relevant steps: {eval_result.relevant_steps}")
        
        involved_steps_list = []
        
        # If we have highlighted evidence, we can create per-step details
        if eval_result.highlighted_evidence:
            # Group evidence by step_index
            steps_evidence = {}
            for evidence in eval_result.highlighted_evidence:
                # Ensure evidence is an object
                ev_obj = evidence
                if isinstance(evidence, dict):
                    ev_obj = EvidenceCitation(**evidence)
                    
                step_idx = ev_obj.step_index
                if step_idx not in steps_evidence:
                    steps_evidence[step_idx] = []
                steps_evidence[step_idx].append(ev_obj)
            
            # Create a StepEvaluationDetail for each step with evidence
            for step_idx, ev_list in steps_evidence.items():
                # Determine status for this step
                step_verdict = None
                for ev in ev_list:
                    if ev.verdict:
                        step_verdict = ev.verdict
                        break
                
                # Fallback to overall verdict if step verdict is missing
                if not step_verdict:
                    step_verdict = EvaluateStatus(eval_result.verdict.lower()) if eval_result.verdict.lower() in ["pass", "fail", "partial"] else EvaluateStatus.UNKNOWN
                
                # Determine reasoning
                step_reasoning = "; ".join([ev.reasoning for ev in ev_list if ev.reasoning])
                if not step_reasoning:
                    step_reasoning = eval_result.reasoning
                    
                # Convert evidence back to dicts
                ev_dicts = [ev.model_dump() for ev in ev_list]
                
                step_detail = StepEvaluationDetail(
                    granularity=target_granularity,
                    evaluateStatus=step_verdict,
                    reasoning=step_reasoning,
                    highlighted_evidence=ev_dicts,
                    confidenceScore=eval_result.confidence_score,
                    steps=[step_idx]
                )
                involved_steps_list.append(step_detail)
        
        # If no evidence or we want to ensure we have at least one detail (e.g. if no steps were highlighted but we have a verdict)
        if not involved_steps_list:
            # Convert EvidenceCitation objects to dicts for Pydantic validation
            evidence_dicts = []
            for evidence in eval_result.highlighted_evidence:
                if isinstance(evidence, EvidenceCitation):
                    evidence_dicts.append(evidence.model_dump())
                else:
                    evidence_dicts.append(evidence)
                    
            step_detail = StepEvaluationDetail(
                granularity=target_granularity,
                evaluateStatus=EvaluateStatus(eval_result.verdict.lower()) if eval_result.verdict.lower() in ["pass", "fail", "partial"] else EvaluateStatus.UNKNOWN,
                reasoning=eval_result.reasoning,
                highlighted_evidence=evidence_dicts,
                confidenceScore=eval_result.confidence_score,
                steps=eval_result.relevant_steps
            )
            involved_steps_list.append(step_detail)
        
        logger.info(f"Created {len(involved_steps_list)} StepEvaluationDetail objects")
        
        # 6. Generate overall assessment using LLM
        logger.info(f"Generating overall assessment for criterion '{crit.title}'")
        overall_assessment, overall_reasoning, confidence = await _generate_overall_assessment(
            criterion_title=crit.title,
            criterion_assertion=crit.assertion,
            criterion_description=crit.description,
            task_name=task.name,
            granularity=target_granularity,
            personas=personas,
            models=models,
            eval_result=eval_result,
            involved_steps=involved_steps_list,
            services=services
        )
        
        return ExperimentCriterionResult(
            title=crit.title,
            assertion=crit.assertion,
            description=crit.description,
            granularity=target_granularity,
            involved_steps=involved_steps_list,
            overall_assessment=overall_assessment,
            overall_reasoning=overall_reasoning,
            confidence=confidence
        )
        
    except Exception as e:
        logger.error(f"Evaluation failed for criterion {crit.title}: {e}")
        return None


async def _load_condition_run_data(
    condition: ConditionRequest,
    history_logs_dir: Path
) -> Optional[Dict]:
    """Load run data for a condition from disk."""
    logger.info(f"Loading data for condition: {condition.conditionID}")
    
    # 1. Load run data using conditionID as filename
    try:
        json_file = history_logs_dir / f"{condition.conditionID}.json"
        if not json_file.exists():
            logger.error(f"Condition file not found: {json_file}")
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
    persona = metadata.get("persona", "")
    personas = [persona] if persona else []
    
    value = metadata.get("value", "")
    
    model = metadata.get("model", "")
    models = [model] if model else []
    
    run_index = metadata.get("run_index", 1)

    logger.info(f"Loaded condition data: persona={persona}, value={value}, model={model}, run_index={run_index}, steps={len(all_steps)}")

    return {
        "conditionID": condition.conditionID,
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
    services: JudgeServices
) -> Tuple[str, Optional[ExperimentCriterionResult]]:
    """Evaluate a single criterion for a loaded condition context."""
    result = await _process_single_criterion(
        crit=criterion,
        task=context["task"],
        all_steps=context["all_steps"],
        personas=context["personas"],
        models=context["models"],
        services=services
    )
    return context["conditionID"], result


from ..services.llm_factory import get_chat_llm
import json
from langchain_core.messages import HumanMessage


async def _rank_conditions_with_llm(
    criterion: ExperimentCriterion,
    condition_evaluations: dict,
    results: List[ConditionResult]
) -> tuple[List[RankingItem], str]:
    """
    Use LLM to rank conditions for a specific criterion.
    
    Args:
        criterion: The criterion being evaluated
        condition_evaluations: Dict mapping condition_id -> ExperimentCriterionResult
        results: List of all ConditionResult objects to extract metadata
        
    Returns:
        Tuple of (ranking_items, reasoning)
    """
    # Build context for LLM
    condition_details = []
    for result in results:
        if result.conditionID not in condition_evaluations:
            continue
        
        crit_result = condition_evaluations[result.conditionID]
        condition_info = {
            "condition_id": result.conditionID,
            "persona": result.persona,
            "value": result.value,
            "model": result.model,
            "run_index": result.run_index,
            "overall_assessment": crit_result.overall_assessment.value,
            "confidence": crit_result.confidence or 0,
            "overall_reasoning": crit_result.overall_reasoning or "",
            "involved_steps_count": len(crit_result.involved_steps),
            "involved_steps_summary": [
                {
                    "granularity": step.granularity.value,
                    "status": step.evaluateStatus.value,
                    "confidence": step.confidenceScore,
                    "reasoning": step.reasoning
                }
                for step in crit_result.involved_steps[:3]  # Top 3 steps for brevity
            ]
        }
        condition_details.append(condition_info)
    
    # Create prompt for LLM
    prompt = f"""You are a professional evaluation expert. Please analyze and rank multiple conditions based on the following information.

Evaluation Criterion:
- Title: {criterion.title}
- Assertion: {criterion.assertion}
- Description: {criterion.description}

Condition Evaluation Details:
{json.dumps(condition_details, indent=2, ensure_ascii=False)}

Tasks:
1. Carefully analyze the performance of each condition
2. Rank conditions based on overall_assessment status (pass > partial > fail) and confidence scores
3. Consider the details and reasoning of involved_steps
4. Generate ranking results and detailed justification
5. Do not include any conditionID in your reasoning instead, refer to their persona/model/run_indexs for clarity.

Please return results in JSON format:
{{
    "ranking": [
        {{
            "rank": 1,
            "condition_id": "...",
            "summary": "Brief performance summary for this condition"
        }},
        ...
    ],
    "reasoning": "Detailed explanation of the ranking order, including strengths and weaknesses of each condition"
}}
"""
    
    try:
        llm = get_chat_llm()
        response = await asyncio.to_thread(
            lambda: llm.invoke([HumanMessage(content=prompt)])
        )
        
        # Parse response
        response_text = response.content
        # Extract JSON from response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            ranking_data = json.loads(json_str)
        else:
            raise ValueError("No JSON found in LLM response")
        
        # Build ranking items
        ranking_items = []
        condition_map = {result.conditionID: result for result in results}
        
        for rank_data in ranking_data.get("ranking", []):
            cond_id = rank_data["condition_id"]
            if cond_id not in condition_map:
                continue
            
            result = condition_map[cond_id]
            crit_result = condition_evaluations[cond_id]
            
            ranking_item = RankingItem(
                rank=rank_data["rank"],
                condition_id=cond_id,
                overall_assessment=crit_result.overall_assessment,
                confidence=crit_result.confidence or 0,
                summary=rank_data.get("summary", ""),
                persona=result.persona,
                value=result.value,
                model=result.model,
                run_index=result.run_index
            )
            ranking_items.append(ranking_item)
        
        reasoning = ranking_data.get("reasoning", "")
        
        return ranking_items, reasoning
        
    except Exception as e:
        logger.error(f"LLM ranking failed: {e}, falling back to default ranking")
        # Fallback to simple ranking if LLM fails
        return _fallback_ranking(condition_evaluations, results), f"Default ranking (LLM failed: {str(e)})"


def _fallback_ranking(
    condition_evaluations: dict,
    results: List[ConditionResult]
) -> List[RankingItem]:
    """
    Fallback ranking when LLM fails.
    
    Priority: pass > partial > fail > unknown, then by confidence score.
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
            -(x[1].confidence or 0)
        )
    )
    
    ranking_items = []
    for rank, (cond_id, crit_result) in enumerate(sorted_conditions, 1):
        result = condition_map[cond_id]
        ranking_item = RankingItem(
            rank=rank,
            condition_id=cond_id,
            overall_assessment=crit_result.overall_assessment,
            confidence=crit_result.confidence or 0,
            summary=f"{crit_result.overall_assessment.value} (confidence: {crit_result.confidence or 0:.2f})",
            persona=result.persona,
            value=result.value,
            model=result.model,
            run_index=result.run_index
        )
        ranking_items.append(ranking_item)
    
    return ranking_items


async def _generate_multi_condition_assessment(
    results: List[ConditionResult],
    criteria: List[ExperimentCriterion]
) -> Optional[MultiConditionAssessment]:
    """
    Generate multi-condition assessment comparing all conditions against each criterion.
    Uses LLM to rank and compare conditions for each criterion.
    
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
        
        # Get the granularity from the first result (should be same across conditions)
        first_granularity = next(iter(criterion_results.values())).granularity
        
        # Use LLM to rank conditions (or fallback to default ranking)
        try:
            ranking_items, ranking_reasoning = await _rank_conditions_with_llm(criterion, criterion_results, results)
        except Exception as e:
            logger.warning(f"Failed to run LLM ranking for criterion '{criterion.title}': {e}")
            ranking_items = _fallback_ranking(criterion_results, results)
            ranking_reasoning = f"Default ranking (LLM failed: {str(e)})"
        
        best_condition_id = ranking_items[0].condition_id if ranking_items else None
        if not best_condition_id:
            continue
        
        # Create comparison summary
        comparison_summary_parts = []
        for item in ranking_items:
            comparison_summary_parts.append(
                f"{item.condition_id}: {item.overall_assessment.value} "
                f"(confidence: {item.confidence:.2f})"
            )
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
            granularity=first_granularity,
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
    logger.info(f"Received experiment evaluation request with {len(request.conditions)} conditions and {len(request.criteria)} criteria")
    
    history_logs_dir = Path(__file__).parent.parent.parent / "history_logs"
    
    # 1. Load data for all conditions concurrently
    load_tasks = []
    for condition in request.conditions:
        load_tasks.append(_load_condition_run_data(condition, history_logs_dir))
    
    loaded_contexts_raw = await asyncio.gather(*load_tasks)
    loaded_contexts = [ctx for ctx in loaded_contexts_raw if ctx is not None]
    
    if not loaded_contexts:
        logger.warning("No valid conditions loaded")
        return ExperimentEvaluationResponse(conditions=[], multi_condition_assessment=None)

    # 2. Flattened Evaluation: Create tasks for all (Condition, Criterion) pairs
    evaluation_tasks = []
    for ctx in loaded_contexts:
        for crit in request.criteria:
            evaluation_tasks.append(
                _evaluate_condition_criterion_pair(ctx, crit, services)
            )
            
    logger.info(f"Starting {len(evaluation_tasks)} concurrent evaluation tasks")
    
    # 3. Execute all evaluations concurrently
    flat_results = await asyncio.gather(*evaluation_tasks)
    
    # 4. Group results by condition
    # Map: conditionID -> List[ExperimentCriterionResult]
    results_by_condition = {ctx["conditionID"]: [] for ctx in loaded_contexts}
    
    for cond_id, result in flat_results:
        if result is not None:
            results_by_condition[cond_id].append(result)
            
    # 5. Build final ConditionResult objects
    condition_results = []
    for ctx in loaded_contexts:
        cond_id = ctx["conditionID"]
        
        # Maintain order of criteria as requested
        current_criteria_results = results_by_condition[cond_id]
        crit_map = {res.title: res for res in current_criteria_results}
        
        sorted_results = []
        for req_crit in request.criteria:
            if req_crit.title in crit_map:
                sorted_results.append(crit_map[req_crit.title])
        
        cr = ConditionResult(
            conditionID=cond_id,
            persona=ctx["persona_str"],
            value=ctx["value_str"],
            model=ctx["model_str"],
            run_index=ctx["run_index"],
            criteria=sorted_results
        )
        condition_results.append(cr)
    
    # 6. Generate multi-condition assessment if there are 2+ conditions
    multi_condition_assessment = await _generate_multi_condition_assessment(condition_results, request.criteria)
    
    # Create response
    response = ExperimentEvaluationResponse(conditions=condition_results, multi_condition_assessment=multi_condition_assessment)
    
    # Print the response
    print("\n" + "="*80)
    print("[EVALUATE-EXPERIMENT RESPONSE]")
    print("="*80)
    print(json.dumps(response.model_dump(mode='json'), indent=2, ensure_ascii=False))
    print("="*80 + "\n")
    logger.info(f"Experiment evaluation response sent with {len(condition_results)} conditions")
        
    return response
