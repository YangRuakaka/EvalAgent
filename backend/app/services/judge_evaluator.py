"""
Service for evaluating agent behavior against criteria using an LLM judge.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..schemas.judge import (
    AggregatedSteps,
    EvaluationResult,
    Granularity,
    JudgeEvaluationReport,
    OverallAssessment,
    TaskDecomposition,
    GranularityRequirement,
    EvidenceCitation,
)
from ..schemas.browser_agent import BrowserAgentTask
from .llm_factory import ChatLLMFactory
from .task_decomposer import TaskDecomposerService
from .granularity_analyzer import GranularityAnalyzerService
from .step_aggregator import StepAggregatorService
from .evaluation_prompts import EvaluationPrompts

logger = logging.getLogger(__name__)


class JudgeEvaluatorService:
    """Service to evaluate agent execution against multiple criteria."""
    
    def __init__(
        self,
        llm_factory: ChatLLMFactory,
        decomposer: TaskDecomposerService,
        granularity_analyzer: GranularityAnalyzerService,
        step_aggregator: StepAggregatorService
    ):
        """Initialize the JudgeEvaluatorService.
        
        Args:
            llm_factory: Factory for creating LLM clients
            decomposer: TaskDecomposerService instance
            granularity_analyzer: GranularityAnalyzerService instance
            step_aggregator: StepAggregatorService instance
        """
        self.llm_factory = llm_factory
        self.decomposer = decomposer
        self.granularity_analyzer = granularity_analyzer
        self.step_aggregator = step_aggregator
        self._setup_evaluation_prompt()
        self._setup_merge_prompt()
    
    def _setup_evaluation_prompt(self) -> None:
        """Setup the prompt templates for criterion evaluation."""
        # Load prompt templates from EvaluationPrompts
        self.step_evaluation_template = EvaluationPrompts.get_step_level_prompt()
        self.phase_evaluation_template = EvaluationPrompts.get_phase_level_prompt()
        self.global_evaluation_template = EvaluationPrompts.get_global_summary_prompt()

    def _setup_merge_prompt(self) -> None:
        """Setup the prompt template for merging multiple evaluation results."""
        self.merge_template = EvaluationPrompts.get_merge_results_prompt()
    
    async def _evaluate_step_async(
        self,
        idx: int,
        step: Dict[str, Any],
        criterion_name: str,
        criterion_assertion: str,
        task_name: str,
        personas_str: str,
        models_str: str,
        model_name: str = "deepseek-chat",
        is_first_step: bool = False
    ) -> EvaluationResult:
        """Asynchronously evaluate a single step against a criterion.
        
        Args:
            idx: Step index
            step: The step data dictionary
            criterion_name: Name of the criterion
            criterion_assertion: How to verify the criterion
            task_name: Name of the task
            personas_str: Formatted personas string
            models_str: Formatted models string
            model_name: LLM model to use
            is_first_step: Whether this is the first step (for logging)
            
        Returns:
            EvaluationResult for this step
        """
        try:
            # Extract fields
            thinking = step.get("thinking", "N/A")
            memory = step.get("memory", "N/A")
            eval_prev = step.get("evaluation_previous_goal", "N/A")
            action = str(step.get("action", "N/A"))
            next_goal = step.get("next_goal", "N/A")

            input_dict = {
                "criterion_name": criterion_name,
                "criterion_assertion": criterion_assertion,
                "task_name": task_name,
                "step_index": idx,
                "thinking": thinking,
                "memory": memory,
                "evaluation_previous_goal": eval_prev,
                "action": action,
                "next_goal": next_goal,
                "personas": personas_str,
                "models": models_str
            }
            
            # Log prompt for the first step only to avoid log spam
            if is_first_step:
                template_to_log = self.step_evaluation_template
                formatted_prompt = template_to_log.format(**input_dict)
                logger.info(f"Formatted prompt (Step {idx}):\n{formatted_prompt}")
                print("\n" + "="*80)
                print(f"[CRITERION EVALUATION] Criterion: {criterion_name}")
                print(f"[GRANULARITY LEVEL] STEP_LEVEL")
                print("="*80)
                print(f"[PROMPT SENT TO LLM (Step {idx})]:")
                print(formatted_prompt)
                print("="*80)
            
            # Get LLM client and invoke
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.step_evaluation_template | llm
            response = chain.invoke(input_dict)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            if is_first_step:
                print("[RESPONSE FROM LLM]:")
                print(response_text)
                print("="*80 + "\n")

            # Create a temporary aggregated steps object for this step to aid parsing/logging
            step_agg = AggregatedSteps(
                granularity=Granularity.STEP_LEVEL,
                aggregated_content=f"Step {idx}",
                step_mapping={f"step_{idx}": [idx]},
                summary_metadata={}
            )
            
            res = self._parse_evaluation_response(
                response_text,
                criterion_name,
                step_agg
            )
            res.used_granularity = Granularity.STEP_LEVEL
            return res
            
        except Exception as e:
            logger.error(f"Error evaluating step {idx}: {e}")
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning=f"Step evaluation failed: {str(e)}",
                confidence_score=0.0,
                used_granularity=Granularity.STEP_LEVEL
            )
    
    async def _evaluate_steps_async(
        self,
        target_indices: List[int],
        all_steps: List[Dict[str, Any]],
        criterion_name: str,
        criterion_assertion: str,
        task_name: str,
        personas: List[str],
        models: List[str],
        model_name: str = "deepseek-chat"
    ) -> List[EvaluationResult]:
        """Evaluate multiple steps concurrently.
        
        Args:
            target_indices: List of step indices to evaluate
            all_steps: All execution steps
            criterion_name: Name of the criterion
            criterion_assertion: How to verify the criterion
            task_name: Name of the task
            personas: List of persona descriptions
            models: List of model names used
            model_name: LLM model to use for evaluation
            
        Returns:
            List of EvaluationResult objects for all steps
        """
        # Format personas and models for prompt
        personas_str = ", ".join(personas) if personas else "None"
        models_str = ", ".join(models) if models else "None"
        
        logger.info(f"Starting concurrent evaluation of {len(target_indices)} steps for criterion '{criterion_name}'")
        
        # Create tasks for concurrent execution
        tasks = []
        for i, idx in enumerate(target_indices):
            if 0 <= idx < len(all_steps):
                step = all_steps[idx]
                is_first = (i == 0)
                task = self._evaluate_step_async(
                    idx=idx,
                    step=step,
                    criterion_name=criterion_name,
                    criterion_assertion=criterion_assertion,
                    task_name=task_name,
                    personas_str=personas_str,
                    models_str=models_str,
                    model_name=model_name,
                    is_first_step=is_first
                )
                tasks.append(task)
        
        # Execute all tasks concurrently
        if tasks:
            results = await asyncio.gather(*tasks)
            logger.info(f"Completed concurrent evaluation of {len(results)} steps")
            return results
        else:
            logger.warning(f"No valid steps found for evaluation")
            return []
    
    async def evaluate_criterion(
        self,
        criterion_name: str,
        criterion_assertion: str,
        aggregated_steps: AggregatedSteps,
        task_name: str,
        personas: List[str],
        models: List[str],
        model_name: str = "deepseek-chat",
        all_steps: Optional[List[Dict[str, Any]]] = None,
        criterion_description: Optional[str] = None
    ) -> EvaluationResult:
        """Evaluate a single criterion against aggregated steps.
        
        Args:
            criterion_name: Name of the criterion
            criterion_assertion: How to verify the criterion
            aggregated_steps: AggregatedSteps at appropriate granularity
            task_name: Name of the task
            personas: List of persona descriptions
            models: List of model names used
            model_name: LLM model to use for evaluation
            all_steps: Optional list of original step dicts for detailed logging
            criterion_description: Optional detailed description of the criterion
            
        Returns:
            EvaluationResult with verdict and reasoning
        """
        
        logger.info(f"Evaluating criterion: {criterion_name}")
        
        # Get LLM client
        llm = self.llm_factory.get_langchain_llm(model_name)
        
        # Format personas and models for prompt
        personas_str = ", ".join(personas) if personas else "None"
        models_str = ", ".join(models) if models else "None"
        
        # Optionally print/inspect original steps for debugging and transparency
        # Note: aggregated_steps.step_mapping is a map from string keys to a list of original step indices
        try:
            step_map = aggregated_steps.step_mapping or {}
        except Exception:
            step_map = {}


        # Log high level aggregated content and step mapping
        logger.debug(f"Aggregated content length: {len(aggregated_steps.aggregated_content) if aggregated_steps and aggregated_steps.aggregated_content else 0}")
        logger.debug(f"Step mapping keys: {list(step_map.keys())}")

        # Build granularity-aware raw context with actual detailed step data
        raw_context = self._build_raw_context(
            aggregated_steps=aggregated_steps,
            all_steps=all_steps,
            step_map=step_map
        )

        # If caller passes through original steps (all_steps), we'll print each referenced step data
        # Otherwise, for STEP_LEVEL we can parse the encoded lines from aggregated_content
        # We'll still always print the mapping and aggregated content summary
        # Detailed step logging
        if all_steps:
            logger.info(f"Detailed steps (from original all_steps):")
            for map_key, map_list in step_map.items():
                logger.info(f"Mapping '{map_key}' references indices: {map_list}")
                
                # Normalize to list
                indices = map_list if isinstance(map_list, list) else [map_list]
                
                for idx in indices:
                    try:
                        if isinstance(idx, (int, str)) and str(idx).isdigit():
                            step_idx = int(idx)
                            if 0 <= step_idx < len(all_steps):
                                step_obj = all_steps[step_idx]
                                # Truncate long fields for readability but still show a lot
                                logger.info(f"Step[{step_idx}] -> {json.dumps(step_obj, ensure_ascii=False)[:2000]}")
                            else:
                                logger.warning(f"Step index {step_idx} out of range")
                        else:
                            logger.debug(f"Skipping non-integer step index: {idx}")
                    except Exception as e:
                        logger.warning(f"Failed to fetch original step {idx} from all_steps: {e}")
        else:
            # No all_steps provided; if STEP_LEVEL then aggregated_content likely has per-step encodings
            # We'll fallback to parsing encoded lines
            try:
                if aggregated_steps.aggregated_content:
                    lines = aggregated_steps.aggregated_content.splitlines()
                    logger.info("Encoded aggregated steps (parsed from aggregated_content):")
                    for line in lines:
                        logger.info(line)
            except Exception:
                logger.debug("Unable to parse aggregated_content for detailed step output")
        try:
            # Select template and prepare input based on granularity
            if aggregated_steps.granularity == Granularity.STEP_LEVEL:
                chain = self.step_evaluation_template | llm
                
                # Find all step indices from step_map
                target_indices = []
                if step_map:
                    for indices in step_map.values():
                        if isinstance(indices, list):
                            target_indices.extend(indices)
                        elif isinstance(indices, int):
                            target_indices.append(indices)
                
                # Deduplicate and sort
                target_indices = sorted(list(set(target_indices)))
                
                if target_indices and all_steps:
                    logger.info(f"Evaluating {len(target_indices)} steps individually for STEP_LEVEL criterion using async")
                    
                    # Use async evaluation for all steps
                    step_results = await self._evaluate_steps_async(
                        target_indices=target_indices,
                        all_steps=all_steps,
                        criterion_name=criterion_name,
                        criterion_assertion=criterion_assertion,
                        task_name=task_name,
                        personas=personas,
                        models=models,
                        model_name=model_name
                    )
                    
                    # Merge results if we have any
                    if step_results:
                        if len(step_results) == 1:
                            return step_results[0]
                        
                        return self._merge_evaluation_results(
                            step_results,
                            criterion_name,
                            Granularity.STEP_LEVEL,
                            criterion_assertion,
                            model_name
                        )
                
                # Fallback if no valid steps found
                return EvaluationResult(
                    criterion_name=criterion_name,
                    verdict="UNABLE_TO_EVALUATE",
                    reasoning="No valid steps found for STEP_LEVEL evaluation",
                    confidence_score=0.0,
                    used_granularity=Granularity.STEP_LEVEL
                )

            elif aggregated_steps.granularity == Granularity.PHASE_LEVEL:
                chain = self.phase_evaluation_template | llm
                input_dict = {
                    "criterion_name": criterion_name,
                    "criterion_assertion": criterion_assertion,
                    "task_name": task_name,
                    "aggregated_steps": aggregated_steps.aggregated_content,
                    "raw_context": raw_context,
                    "personas": personas_str,
                    "models": models_str
                }
                template_to_log = self.phase_evaluation_template
            else: # GLOBAL_SUMMARY
                chain = self.global_evaluation_template | llm
                input_dict = {
                    "criterion_name": criterion_name,
                    "criterion_assertion": criterion_assertion,
                    "task_name": task_name,
                    "aggregated_steps": aggregated_steps.aggregated_content,
                    "raw_context": raw_context,
                    "personas": personas_str,
                    "models": models_str
                }
                template_to_log = self.global_evaluation_template
            
            formatted_prompt = template_to_log.format(**input_dict)
            logger.info(f"Formatted prompt:\n{formatted_prompt}")
            print("\n" + "="*80)
            print(f"[CRITERION EVALUATION] Criterion: {criterion_name}")
            print(f"[GRANULARITY LEVEL] {aggregated_steps.granularity.value}")
            print("="*80)
            print("[PROMPT SENT TO LLM]:")
            print(formatted_prompt)
            print("="*80)
            
            response = chain.invoke(input_dict)
            
            response_text = response.content if hasattr(response, 'content') else str(response)
            print("[RESPONSE FROM LLM]:")
            print(response_text)
            print("="*80 + "\n")
            logger.info(f"LLM Response for criterion '{criterion_name}':\n{response_text}")
            
            result = self._parse_evaluation_response(
                response_text,
                criterion_name,
                aggregated_steps
            )
            result.used_granularity = aggregated_steps.granularity
            return result
            
        except Exception as e:
            logger.error(f"Error evaluating criterion {criterion_name}: {e}")
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning=f"Evaluation failed due to error: {str(e)}",
                confidence_score=0.0,
                aggregated_step_summary=aggregated_steps.aggregated_content[:200],
                used_granularity=aggregated_steps.granularity
            )
    
    def _evaluate_step_level(
        self,
        criterion_name: str,
        criterion_assertion: str,
        aggregated_steps: AggregatedSteps,
        task_name: str,
        personas: List[str],
        models: List[str],
        all_steps: Optional[List[Dict[str, Any]]],
        model_name: str
    ) -> EvaluationResult:
        """Evaluate criterion at STEP_LEVEL granularity (single step only).
        
        At STEP_LEVEL, the evaluator can only see the specific step being evaluated,
        with no access to other steps in the execution trace. This is useful for
        evaluating criteria focused on individual step quality.
        
        Args:
            criterion_name: Name of the criterion
            criterion_assertion: How to verify the criterion
            aggregated_steps: Single step aggregation at STEP_LEVEL
            task_name: Name of the task
            personas: List of persona descriptions
            models: List of model names used
            all_steps: All original steps (for context building)
            model_name: LLM model to use for evaluation
            
        Returns:
            EvaluationResult for this step
        """
        logger.info(f"[STEP_LEVEL] Evaluating criterion '{criterion_name}' on single step")
        
        try:
            step_map = aggregated_steps.step_mapping or {}
            
            # Identify the step index. aggregated_steps for step level usually has one step.
            target_indices = []
            if step_map:
                for indices in step_map.values():
                    if isinstance(indices, list):
                        target_indices.extend(indices)
                    elif isinstance(indices, int):
                        target_indices.append(indices)
            
            step_idx = "Unknown"
            thinking = "N/A"
            memory = "N/A"
            eval_prev = "N/A"
            action = "N/A"
            next_goal = "N/A"

            if target_indices and all_steps:
                idx = target_indices[0] # Take the first one
                if 0 <= idx < len(all_steps):
                    step = all_steps[idx]
                    step_idx = idx
                    thinking = step.get("thinking", "N/A")
                    memory = step.get("memory", "N/A")
                    eval_prev = step.get("evaluation_previous_goal", "N/A")
                    action = str(step.get("action", "N/A"))
                    next_goal = step.get("next_goal", "N/A")
            
            # Get LLM client
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.step_evaluation_template | llm
            
            # Format personas and models
            personas_str = ", ".join(personas) if personas else "None"
            models_str = ", ".join(models) if models else "None"
            
            # Build and invoke prompt
            invoke_dict = {
                "criterion_name": criterion_name,
                "criterion_assertion": criterion_assertion,
                "task_name": task_name,
                "step_index": step_idx,
                "thinking": thinking,
                "memory": memory,
                "evaluation_previous_goal": eval_prev,
                "action": action,
                "next_goal": next_goal,
                "personas": personas_str,
                "models": models_str
            }
            
            formatted_prompt = self.step_evaluation_template.format(**invoke_dict)
            print("\n" + "="*80)
            print("[JudgeEvaluatorService._evaluate_step_level]")
            print("="*80)
            print("[PROMPT SENT TO LLM]:")
            print(formatted_prompt)
            print("="*80)
            
            response = chain.invoke(invoke_dict)
            
            response_text = response.content if hasattr(response, 'content') else str(response)
            print("[RESPONSE FROM LLM]:")
            print(response_text)
            print("="*80 + "\n")
            logger.debug(f"Step-level evaluation response: {response_text[:200]}...")
            
            result = self._parse_evaluation_response(
                response_text,
                criterion_name,
                aggregated_steps
            )
            result.used_granularity = Granularity.STEP_LEVEL
            return result
            
        except Exception as e:
            logger.error(f"Step-level evaluation failed for '{criterion_name}': {e}")
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning=f"Step-level evaluation failed: {str(e)}",
                confidence_score=0.0,
                aggregated_step_summary=aggregated_steps.aggregated_content[:200],
                used_granularity=Granularity.STEP_LEVEL
            )
    
    def _evaluate_phase_level(
        self,
        criterion_name: str,
        criterion_assertion: str,
        aggregated_steps: AggregatedSteps,
        task_name: str,
        personas: List[str],
        models: List[str],
        all_steps: Optional[List[Dict[str, Any]]],
        model_name: str
    ) -> EvaluationResult:
        """Evaluate criterion at PHASE_LEVEL granularity (single phase/cluster only).
        
        At PHASE_LEVEL, the evaluator can only see steps within the current phase/cluster,
        along with the phase summary. This is useful for evaluating criteria focused on
        specific phases or sub-tasks.
        
        Args:
            criterion_name: Name of the criterion
            criterion_assertion: How to verify the criterion
            aggregated_steps: Phase/cluster aggregation at PHASE_LEVEL
            task_name: Name of the task
            personas: List of persona descriptions
            models: List of model names used
            all_steps: All original steps (for context building)
            model_name: LLM model to use for evaluation
            
        Returns:
            EvaluationResult for this phase
        """
        logger.info(f"[PHASE_LEVEL] Evaluating criterion '{criterion_name}' on single phase")
        
        try:
            step_map = aggregated_steps.step_mapping or {}
            
            # Build phase-level context (only the phase and its steps)
            raw_context = self._build_phase_level_context(all_steps or [], step_map, aggregated_steps)
            
            # Build step fields description
            
            # Get LLM client
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.phase_evaluation_template | llm
            
            # Format personas and models
            personas_str = ", ".join(personas) if personas else "None"
            models_str = ", ".join(models) if models else "None"
            
            # Build and invoke prompt
            invoke_dict = {
                "criterion_name": criterion_name,
                "criterion_assertion": criterion_assertion,
                "task_name": task_name,
                "aggregated_steps": aggregated_steps.aggregated_content,
                "raw_context": raw_context,
                "personas": personas_str,
                "models": models_str
            }
            
            formatted_prompt = self.phase_evaluation_template.format(**invoke_dict)
            print("\n" + "="*80)
            print("[JudgeEvaluatorService._evaluate_phase_level]")
            print("="*80)
            print("[PROMPT SENT TO LLM]:")
            print(formatted_prompt)
            print("="*80)
            
            response = chain.invoke(invoke_dict)
            
            response_text = response.content if hasattr(response, 'content') else str(response)
            print("[RESPONSE FROM LLM]:")
            print(response_text)
            print("="*80 + "\n")
            logger.debug(f"Phase-level evaluation response: {response_text[:200]}...")
            
            result = self._parse_evaluation_response(
                response_text,
                criterion_name,
                aggregated_steps
            )
            result.used_granularity = Granularity.PHASE_LEVEL
            return result
            
        except Exception as e:
            logger.error(f"Phase-level evaluation failed for '{criterion_name}': {e}")
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning=f"Phase-level evaluation failed: {str(e)}",
                confidence_score=0.0,
                aggregated_step_summary=aggregated_steps.aggregated_content[:200],
                used_granularity=Granularity.PHASE_LEVEL
            )
    
    async def _evaluate_phase_level_async(
        self,
        criterion_name: str,
        criterion_assertion: str,
        aggregated_steps: AggregatedSteps,
        task_name: str,
        personas: List[str],
        models: List[str],
        all_steps: Optional[List[Dict[str, Any]]],
        model_name: str
    ) -> EvaluationResult:
        """Async version of _evaluate_phase_level for concurrent phase evaluation.
        
        Evaluates criterion at PHASE_LEVEL granularity asynchronously.
        
        Args:
            criterion_name: Name of the criterion
            criterion_assertion: How to verify the criterion
            aggregated_steps: Phase/cluster aggregation at PHASE_LEVEL
            task_name: Name of the task
            personas: List of persona descriptions
            models: List of model names used
            all_steps: All original steps (for context building)
            model_name: LLM model to use for evaluation
            
        Returns:
            EvaluationResult for this phase
        """
        logger.info(f"[PHASE_LEVEL_ASYNC] Evaluating criterion '{criterion_name}' on single phase")
        
        try:
            step_map = aggregated_steps.step_mapping or {}
            
            # Build phase-level context (only the phase and its steps)
            raw_context = self._build_phase_level_context(all_steps or [], step_map, aggregated_steps)
            
            # Build step fields description
            
            # Get LLM client
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.phase_evaluation_template | llm
            
            # Format personas and models
            personas_str = ", ".join(personas) if personas else "None"
            models_str = ", ".join(models) if models else "None"
            
            # Build and invoke prompt
            invoke_dict = {
                "criterion_name": criterion_name,
                "criterion_assertion": criterion_assertion,
                "task_name": task_name,
                "aggregated_steps": aggregated_steps.aggregated_content,
                "raw_context": raw_context,
                "personas": personas_str,
                "models": models_str
            }
            
            formatted_prompt = self.phase_evaluation_template.format(**invoke_dict)
            print("\n" + "="*80)
            print("[JudgeEvaluatorService._evaluate_phase_level_async]")
            print("="*80)
            print("[PROMPT SENT TO LLM]:")
            print(formatted_prompt)
            print("="*80)
            
            response = chain.invoke(invoke_dict)
            
            response_text = response.content if hasattr(response, 'content') else str(response)
            print("[RESPONSE FROM LLM]:")
            print(response_text)
            print("="*80 + "\n")
            logger.debug(f"Phase-level async evaluation response: {response_text[:200]}...")
            
            result = self._parse_evaluation_response(
                response_text,
                criterion_name,
                aggregated_steps
            )
            result.used_granularity = Granularity.PHASE_LEVEL
            return result
            
        except Exception as e:
            logger.error(f"Phase-level async evaluation failed for '{criterion_name}': {e}")
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning=f"Phase-level async evaluation failed: {str(e)}",
                confidence_score=0.0,
                aggregated_step_summary=aggregated_steps.aggregated_content[:200],
                used_granularity=Granularity.PHASE_LEVEL
            )
    
    def _evaluate_global_summary(
        self,
        criterion_name: str,
        criterion_assertion: str,
        aggregated_steps: AggregatedSteps,
        task_name: str,
        personas: List[str],
        models: List[str],
        all_steps: Optional[List[Dict[str, Any]]],
        model_name: str
    ) -> EvaluationResult:
        """Evaluate criterion at GLOBAL_SUMMARY granularity (complete execution trace).
        
        At GLOBAL_SUMMARY, the evaluator can see the complete execution trace with all steps.
        This is useful for evaluating criteria about overall task completion, strategy, or
        consistency across the entire execution.
        
        Args:
            criterion_name: Name of the criterion
            criterion_assertion: How to verify the criterion
            aggregated_steps: Complete aggregation at GLOBAL_SUMMARY
            task_name: Name of the task
            personas: List of persona descriptions
            models: List of model names used
            all_steps: All original steps (for context building)
            model_name: LLM model to use for evaluation
            
        Returns:
            EvaluationResult for the complete execution
        """
        logger.info(f"[GLOBAL_SUMMARY] Evaluating criterion '{criterion_name}' on complete execution")
        
        try:
            # Build global context (all steps)
            raw_context = self._build_global_context(all_steps or [])
            
            
            # Get LLM client
            llm = self.llm_factory.get_langchain_llm(model_name)
            chain = self.global_evaluation_template | llm
            
            # Format personas and models
            personas_str = ", ".join(personas) if personas else "None"
            models_str = ", ".join(models) if models else "None"
            
            # Build and invoke prompt
            invoke_dict = {
                "criterion_name": criterion_name,
                "criterion_assertion": criterion_assertion,
                "task_name": task_name,
                "aggregated_steps": aggregated_steps.aggregated_content,
                "raw_context": raw_context,
                "personas": personas_str,
                "models": models_str
            }
            
            formatted_prompt = self.global_evaluation_template.format(**invoke_dict)
            print("\n" + "="*80)
            print("[JudgeEvaluatorService._evaluate_global_summary]")
            print("="*80)
            print("[PROMPT SENT TO LLM]:")
            print(formatted_prompt)
            print("="*80)
            
            response = chain.invoke(invoke_dict)
            
            response_text = response.content if hasattr(response, 'content') else str(response)
            print("[RESPONSE FROM LLM]:")
            print(response_text)
            print("="*80 + "\n")
            logger.debug(f"Global-level evaluation response: {response_text[:200]}...")
            
            result = self._parse_evaluation_response(
                response_text,
                criterion_name,
                aggregated_steps
            )
            result.used_granularity = Granularity.GLOBAL_SUMMARY
            return result
            
        except Exception as e:
            logger.error(f"Global-level evaluation failed for '{criterion_name}': {e}")
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning=f"Global-level evaluation failed: {str(e)}",
                confidence_score=0.0,
                aggregated_step_summary=aggregated_steps.aggregated_content[:200],
                used_granularity=Granularity.GLOBAL_SUMMARY
            )
    
    async def _evaluate_single_criterion_process(
        self,
        criterion: Dict[str, str],
        req: GranularityRequirement,
        task: BrowserAgentTask,
        all_steps: List[Dict[str, Any]],
        personas: List[str],
        models: List[str],
        evaluator_model: str,
        task_decomposition: TaskDecomposition
    ) -> EvaluationResult:
        """Process a single criterion evaluation asynchronously.
        
        Args:
            criterion: The criterion dictionary
            req: Granularity requirement for this criterion
            task: The task definition
            all_steps: All execution steps
            personas: List of personas
            models: List of models
            evaluator_model: Model to use for evaluation
            task_decomposition: Task decomposition result
            
        Returns:
            EvaluationResult for this criterion
        """
        try:
            granularity = req.required_granularity
            criterion_name = criterion.get("name", "unknown")
            criterion_desc = criterion.get("description", "")
            criterion_assertion = criterion.get("assertion", "")
            
            if granularity == Granularity.STEP_LEVEL:
                # Determine which steps to evaluate
                target_indices = req.target_step_indices
                
                # If target_indices is empty, it usually implies evaluating all steps (default behavior)
                # However, if the LLM explicitly meant "no steps", we should handle that. 
                # Can't distinguish easily without more flags. Assuming empty -> all for safety.
                if not target_indices:
                    target_indices = list(range(len(all_steps)))
                else:
                    # Filter out out-of-bounds indices
                    target_indices = [i for i in target_indices if 0 <= i < len(all_steps)]
                    # If valid indices provided are none, fallback to all? Or respect empty?
                    # If LLM gave [100] (invalid) -> empty. Fallback to all.
                    if not target_indices:
                        target_indices = list(range(len(all_steps)))

                # Evaluate each step individually using step-level evaluator with async concurrency
                logger.info(f"Evaluating criterion '{criterion_name}' at STEP_LEVEL using async concurrency (Indices: {target_indices})")
                step_results = await self._evaluate_steps_async(
                    target_indices=target_indices,
                    all_steps=all_steps,
                    criterion_name=criterion_name,
                    criterion_assertion=criterion_assertion,
                    task_name=task.name,
                    personas=personas,
                    models=models,
                    model_name=evaluator_model
                )
                
                # Merge results
                final_result = self._merge_evaluation_results(
                    step_results,
                    criterion_name,
                    Granularity.STEP_LEVEL,
                    criterion_assertion,
                    evaluator_model
                )
                return final_result
                
            elif granularity == Granularity.PHASE_LEVEL:
                # Evaluate each cluster using phase-level evaluator with async concurrency
                logger.info(f"Evaluating criterion '{criterion_name}' at PHASE_LEVEL using async concurrency")
                
                # Determine which clusters to evaluate
                target_cluster_indices = req.target_cluster_indices if req.target_cluster_indices else list(range(len(task_decomposition.subtask_clusters)))
                
                logger.info(f"Target cluster indices for this criterion: {target_cluster_indices}")
                
                cluster_tasks = []
                for cluster_idx in target_cluster_indices:
                    if cluster_idx < len(task_decomposition.subtask_clusters):
                        cluster = task_decomposition.subtask_clusters[cluster_idx]
                        
                        # Get raw steps for this cluster
                        cluster_steps = [all_steps[i] for i in cluster.step_indices if i < len(all_steps)]
                        cluster_steps_str = json.dumps(cluster_steps, ensure_ascii=False, indent=2)
                        
                        content = f"Cluster Summary: {cluster.cluster_summary}\n\nRaw Steps:\n{cluster_steps_str}"
                        
                        agg = AggregatedSteps(
                            granularity=Granularity.PHASE_LEVEL,
                            aggregated_content=content,
                            step_mapping={cluster.cluster_id: cluster.step_indices},
                            summary_metadata={"cluster_id": cluster.cluster_id}
                        )
                        
                        # Create async task for this cluster
                        task_coro = self._evaluate_phase_level_async(
                            criterion_name=criterion_name,
                            criterion_assertion=criterion_assertion,
                            aggregated_steps=agg,
                            task_name=task.name,
                            personas=personas,
                            models=models,
                            all_steps=all_steps,
                            model_name=evaluator_model
                        )
                        cluster_tasks.append(task_coro)
                
                # Execute all cluster evaluations concurrently (only for target clusters)
                cluster_results = await asyncio.gather(*cluster_tasks) if cluster_tasks else []
                
                # If no clusters were evaluated, create a failed result
                if not cluster_results:
                    logger.warning(f"No valid clusters found to evaluate for criterion '{criterion_name}'")
                    cluster_results = [EvaluationResult(
                        criterion_name=criterion_name,
                        verdict="UNABLE_TO_EVALUATE",
                        reasoning="No valid clusters found for evaluation",
                        confidence_score=0.0,
                        used_granularity=Granularity.PHASE_LEVEL
                    )]
                    
                # Merge results
                final_result = self._merge_evaluation_results(
                    cluster_results,
                    criterion_name,
                    Granularity.PHASE_LEVEL,
                    criterion_assertion,
                    evaluator_model
                )
                return final_result
                
            else:  # GLOBAL_SUMMARY
                # Use global-level evaluator for complete execution
                logger.info(f"Evaluating criterion '{criterion_name}' at GLOBAL_SUMMARY")
                # Aggregate all steps for global context
                agg = self.step_aggregator.aggregate_steps(
                    all_steps=all_steps,
                    granularity=Granularity.GLOBAL_SUMMARY,
                    task_decomposition=task_decomposition,
                    task_name=task.name,
                    model_name=evaluator_model
                )
                
                result = await self.evaluate_criterion(
                    criterion_name=criterion_name,
                    criterion_assertion=criterion_assertion,
                    aggregated_steps=agg,
                    task_name=task.name,
                    personas=personas,
                    models=models,
                    model_name=evaluator_model,
                    all_steps=all_steps,
                    criterion_description=criterion_desc
                )
                return result

        except Exception as e:
            logger.error(f"Criterion evaluation failed for {criterion.get('name')}: {e}")
            return EvaluationResult(
                criterion_name=criterion.get("name", "unknown"),
                verdict="UNABLE_TO_EVALUATE",
                reasoning=f"Evaluation failed: {str(e)}",
                confidence_score=0.0,
                aggregated_step_summary="Evaluation failed",
                used_granularity=req.required_granularity
            )

    async def evaluate_batch(
        self,
        run_id: str,
        criteria: List[Dict[str, str]],
        task: BrowserAgentTask,
        all_steps: List[Dict[str, Any]],
        personas: List[str],
        models: List[str],
        decomposer_model: str = "deepseek-chat",
        evaluator_model: str = "deepseek-chat",
        cache_decomposition: bool = True
    ) -> JudgeEvaluationReport:
        """Evaluate multiple criteria against a run's execution.
        
        Args:
            run_id: ID of the agent run
            criteria: List of criteria dicts with name, description, assertion
            task: BrowserAgentTask definition
            all_steps: All execution steps from the run
            personas: Personas used in the run
            models: Models used in the run
            decomposer_model: Model to use for task decomposition
            evaluator_model: Model to use for evaluation
            cache_decomposition: Whether to cache task decomposition
            
        Returns:
            JudgeEvaluationReport with all evaluation results
        """
        
        logger.info(f"Starting batch evaluation for run: {run_id} with {len(criteria)} criteria")
        
        # Step 1: Task decomposition
        logger.info("Step 1: Decomposing task...")
        try:
            task_decomposition = self.decomposer.decompose_execution_steps(
                task=task,
                all_steps=all_steps,
                run_metadata={"run_id": run_id},
                model_name=decomposer_model
            )
        except Exception as e:
            logger.error(f"Task decomposition failed: {e}")
            # Create minimal decomposition
            from ..schemas.judge import StepCluster
            task_decomposition = TaskDecomposition(
                task_name=task.name,
                subtask_clusters=[
                    StepCluster(
                        cluster_id="cluster_0",
                        semantic_label="Task Execution",
                        step_indices=list(range(len(all_steps))),
                        cluster_summary="Complete task execution",
                        key_decisions=[],
                        dependencies=[]
                    )
                ],
                total_steps=len(all_steps)
            )
        
        # Step 2: Analyze granularity for each criterion
        logger.info("Step 2: Analyzing granularity requirements...")
        granularity_requirements: List[GranularityRequirement] = []
        for criterion in criteria:
            try:
                requirement = self.granularity_analyzer.analyze_criterion_granularity(
                    criterion_name=criterion.get("name", "unknown"),
                    criterion_assertion=criterion.get("assertion", ""),
                    task_name=task.name,
                    model_name=evaluator_model,
                    task_decomposition=task_decomposition
                )
                granularity_requirements.append(requirement)
            except Exception as e:
                logger.warning(f"Granularity analysis failed for {criterion.get('name')}: {e}")
                # Provide default
                granularity_requirements.append(GranularityRequirement(
                    criterion_name=criterion.get("name", "unknown"),
                    required_granularity=Granularity.PHASE_LEVEL,
                    rationale="Default granularity assigned due to analysis error",
                    target_cluster_indices=[]
                ))
        
        # Step 3: Evaluate each criterion based on granularity
        logger.info("Step 3: Evaluating criteria...")
        
        # Create tasks for all criteria
        criterion_tasks = []
        for criterion, req in zip(criteria, granularity_requirements):
            task_coro = self._evaluate_single_criterion_process(
                criterion=criterion,
                req=req,
                task=task,
                all_steps=all_steps,
                personas=personas,
                models=models,
                evaluator_model=evaluator_model,
                task_decomposition=task_decomposition
            )
            criterion_tasks.append(task_coro)
            
        # Run all criteria evaluations concurrently
        evaluation_results = await asyncio.gather(*criterion_tasks)
        
        # Step 4: Create overall assessment
        logger.info("Step 4: Creating overall assessment...")
        overall_assessment = self._create_overall_assessment(evaluation_results)
        
        # Step 5: Create final report
        report = JudgeEvaluationReport(
            run_id=run_id,
            evaluation_timestamp=datetime.utcnow(),
            task_decomposition=task_decomposition,
            evaluation_results=evaluation_results,
            granularity_analysis=granularity_requirements,
            overall_assessment=overall_assessment,
            metadata={
                "decomposer_model": decomposer_model,
                "evaluator_model": evaluator_model,
                "total_steps": len(all_steps),
                "cache_decomposition": cache_decomposition
            }
        )
        
        logger.info(f"Batch evaluation complete for run: {run_id}")
        return report
    
    def _normalize_source_field(self, field_name: str) -> str:
        """Normalize source field names from snake_case to PascalCase enum values.
        
        Maps common field name variations to AgentStepField enum values.
        
        Args:
            field_name: The field name (often in snake_case from LLM output)
            
        Returns:
            The corresponding AgentStepField enum value in PascalCase
        """
        field_lower = field_name.lower().strip()
        
        # Map various field name formats to enum values
        mapping = {
            'evaluation': 'Evaluation',
            'memory': 'Memory',
            'thinking_process': 'Thinking Process',
            'thinking': 'Thinking Process',
            'next_goal': 'Next Goal',
            'next_action': 'Next Goal',
            'action': 'Action',
            'execution': 'Action',
        }
        
        return mapping.get(field_lower, 'Evaluation')
    
    def _parse_evaluation_response(
        self,
        response_text: str,
        criterion_name: str,
        aggregated_steps: AggregatedSteps
    ) -> EvaluationResult:
        """Parse LLM evaluation response into EvaluationResult.
        
        Args:
            response_text: Raw LLM response
            criterion_name: Name of the criterion
            aggregated_steps: Steps that were evaluated
            
        Returns:
            EvaluationResult object
        """
        
        try:
            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("Could not find JSON in evaluation response")
                return self._create_default_evaluation_result(criterion_name, aggregated_steps)
            
            json_str = response_text[json_start:json_end]
            response_data = json.loads(json_str)
            
            print("\n" + "-"*80)
            print(f"[PARSED JSON RESPONSE] for criterion '{criterion_name}':")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
            print("-"*80 + "\n")
            logger.info(f"Parsed JSON response:\n{json.dumps(response_data, indent=2, ensure_ascii=False)}")
            
            # Parse highlighted evidence
            highlighted_evidence = []
            if "highlighted_evidence" in response_data:
                print(f"[EVIDENCE PARSING] Found {len(response_data['highlighted_evidence'])} evidence items:")
                for idx, item in enumerate(response_data["highlighted_evidence"]):
                    print(f"  Evidence {idx}: {item}")
                    try:
                        # Normalize source_field from snake_case to PascalCase enum value
                        if "source_field" in item and isinstance(item["source_field"], str):
                            item["source_field"] = self._normalize_source_field(item["source_field"])
                        
                        # Handle verdict case conversion if present
                        if "verdict" in item and isinstance(item["verdict"], str):
                            item["verdict"] = item["verdict"].lower()

                        evidence_obj = EvidenceCitation(**item)
                        highlighted_evidence.append(evidence_obj)
                        print(f"    ✓ Successfully parsed as EvidenceCitation")
                    except Exception as e:
                        logger.warning(f"Failed to parse evidence item: {e}")
                        print(f"    ✗ Error parsing: {e}")
                print()

            result = EvaluationResult(
                criterion_name=criterion_name,
                verdict=response_data.get("verdict", "UNABLE_TO_EVALUATE"),
                reasoning=response_data.get("reasoning", ""),
                confidence_score=float(response_data.get("confidence_score", 0.5)),
                relevant_steps=response_data.get("relevant_steps", []),
                aggregated_step_summary=aggregated_steps.aggregated_content[:500],
                used_granularity=aggregated_steps.granularity,
                supporting_evidence=response_data.get("supporting_evidence", ""),
                highlighted_evidence=highlighted_evidence
            )
            
            logger.debug(f"[FINAL RESULT] EvaluationResult created: Verdict={result.verdict}, Confidence={result.confidence_score}, Evidence Count={len(result.highlighted_evidence)}")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse evaluation JSON: {e}")
            return self._create_default_evaluation_result(criterion_name, aggregated_steps)
    
    def _create_default_evaluation_result(
        self,
        criterion_name: str,
        aggregated_steps: AggregatedSteps
    ) -> EvaluationResult:
        """Create a default evaluation result when parsing fails.
        
        Args:
            criterion_name: Name of the criterion
            aggregated_steps: Steps that were evaluated
            
        Returns:
            Default EvaluationResult
        """
        
        return EvaluationResult(
            criterion_name=criterion_name,
            verdict="UNABLE_TO_EVALUATE",
            reasoning="Evaluation parsing failed",
            confidence_score=0.0,
            aggregated_step_summary=aggregated_steps.aggregated_content[:200],
            used_granularity=aggregated_steps.granularity
        )
    
    def _create_overall_assessment(
        self,
        evaluation_results: List[EvaluationResult]
    ) -> OverallAssessment:
        """Create an overall assessment from individual evaluation results.
        
        Args:
            evaluation_results: List of evaluation results
            
        Returns:
            OverallAssessment summarizing all evaluations
        """
        
        total = len(evaluation_results)
        passed = sum(1 for r in evaluation_results if r.verdict == "PASS")
        failed = sum(1 for r in evaluation_results if r.verdict == "FAIL")
        partial = sum(1 for r in evaluation_results if r.verdict == "PARTIAL")
        unable = sum(1 for r in evaluation_results if r.verdict == "UNABLE_TO_EVALUATE")
        
        avg_confidence = (
            sum(r.confidence_score for r in evaluation_results) / total
            if total > 0
            else 0.0
        )
        
        # Generate summary
        pass_rate = (passed / total * 100) if total > 0 else 0
        summary = (
            f"Evaluation completed with {passed} passed, {failed} failed, "
            f"{partial} partial, and {unable} unable to evaluate out of {total} criteria "
            f"(pass rate: {pass_rate:.1f}%). Average confidence: {avg_confidence:.2f}"
        )
        
        return OverallAssessment(
            total_criteria=total,
            passed_count=passed,
            failed_count=failed,
            partial_count=partial,
            unable_to_evaluate_count=unable,
            average_confidence=avg_confidence,
            overall_summary=summary
        )
    
    def _merge_evaluation_results(
        self,
        results: List[EvaluationResult],
        criterion_name: str,
        granularity: Granularity,
        criterion_assertion: str = "",
        model_name: str = "gpt-4o-mini"  # Optimized: faster/cheaper for aggregation
    ) -> EvaluationResult:
        """Merge multiple evaluation results using LLM aggregation."""
        if not results:
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict="UNABLE_TO_EVALUATE",
                reasoning="No results to merge",
                confidence_score=0.0,
                used_granularity=granularity
            )
            
        # Build individual verdicts string
        verdicts_str = ""
        for i, result in enumerate(results):
            verdicts_str += f"\nEvaluation {i+1}:\n"
            verdicts_str += f"  Verdict: {result.verdict}\n"
            verdicts_str += f"  Confidence: {result.confidence_score}\n"
            verdicts_str += f"  Reasoning: {result.reasoning}\n"
        
        # Determine granularity type string
        granularity_type = "STEP_LEVEL" if granularity == Granularity.STEP_LEVEL else "PHASE_LEVEL"
        
        try:
            # Get LLM client
            llm = self.llm_factory.get_langchain_llm(model_name)
            
            # Create merge chain
            chain = self.merge_template | llm
            
            # Invoke LLM to merge verdicts
            invoke_dict = {
                "criterion_name": criterion_name,
                "criterion_assertion": criterion_assertion,
                "granularity_type": granularity_type,
                "individual_verdicts": verdicts_str
            }
            
            formatted_prompt = self.merge_template.format(**invoke_dict)
            print("\n" + "="*80)
            print("[JudgeEvaluatorService._merge_evaluation_results]")
            print("="*80)
            print("[PROMPT SENT TO LLM]:")
            print(formatted_prompt)
            print("="*80)
            
            response = chain.invoke(invoke_dict)
            
            response_text = response.content if hasattr(response, 'content') else str(response)
            print("[RESPONSE FROM LLM]:")
            print(response_text)
            print("="*80 + "\n")
            
            # Parse the merge response
            merged_result = self._parse_merge_response(
                response_text,
                criterion_name,
                results,
                granularity
            )
            
            # Print final merged result summary (only once per criterion)
            print(f"\n[MERGED RESULT] Final evaluation for criterion '{criterion_name}':")
            print(f"  Verdict: {merged_result.verdict}")
            print(f"  Confidence: {merged_result.confidence_score}")
            print(f"  Highlighted Evidence Count: {len(merged_result.highlighted_evidence)}")
            print(f"  (Merged {len(results)} individual evaluations)\n")
            
            return merged_result
            
        except Exception as e:
            logger.warning(f"LLM merge failed: {e}, falling back to simple aggregation")
            # Fallback: simple logic-based merge
            fallback_result = self._simple_merge_results(results, criterion_name, granularity)
            
            # Print fallback merged result summary
            print(f"\n[MERGED RESULT] Final evaluation for criterion '{criterion_name}' (fallback):")
            print(f"  Verdict: {fallback_result.verdict}")
            print(f"  Confidence: {fallback_result.confidence_score}")
            print(f"  Highlighted Evidence Count: {len(fallback_result.highlighted_evidence)}")
            print(f"  (Merged {len(results)} individual evaluations)\n")
            
            return fallback_result
    
    def _parse_merge_response(
        self,
        response_text: str,
        criterion_name: str,
        results: List[EvaluationResult],
        granularity: Granularity
    ) -> EvaluationResult:
        """Parse LLM merge response into EvaluationResult."""
        try:
            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("Could not find JSON in merge response")
                return self._simple_merge_results(results, criterion_name, granularity)
            
            json_str = response_text[json_start:json_end]
            response_data = json.loads(json_str)
            
            # Aggregate highlighted evidence from all results
            aggregated_evidence = []
            for result in results:
                if result.highlighted_evidence:
                    aggregated_evidence.extend(result.highlighted_evidence)
            
            logger.info(f"Aggregated {len(aggregated_evidence)} evidence items from {len(results)} results")
            
            return EvaluationResult(
                criterion_name=criterion_name,
                verdict=response_data.get("verdict", "UNABLE_TO_EVALUATE"),
                reasoning=response_data.get("reasoning", ""),
                confidence_score=float(response_data.get("confidence_score", 0.5)),
                aggregated_step_summary=response_data.get("aggregation_summary", ""),
                used_granularity=granularity,
                highlighted_evidence=aggregated_evidence
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse merge JSON: {e}")
            return self._simple_merge_results(results, criterion_name, granularity)
    
    def _simple_merge_results(
        self,
        results: List[EvaluationResult],
        criterion_name: str,
        granularity: Granularity
    ) -> EvaluationResult:
        """Simple logic-based merge as fallback when LLM merge fails."""
        verdicts = [r.verdict for r in results]
        passed = verdicts.count("PASS")
        failed = verdicts.count("FAIL")
        partial = verdicts.count("PARTIAL")
        total = len(results)
        
        # Determine verdict based on counts
        if failed > 0:
            final_verdict = "FAIL"
        elif partial > 0:
            final_verdict = "PARTIAL"
        elif passed == total:
            final_verdict = "PASS"
        else:
            final_verdict = "UNABLE_TO_EVALUATE"
        
        pass_rate = passed / total if total > 0 else 0
        avg_confidence = sum(r.confidence_score for r in results) / len(results)
        
        reasoning = f"Merged {total} evaluations: {passed} passed, {failed} failed, {partial} partial. Pass rate: {pass_rate:.1%}"
        
        # Aggregate highlighted evidence from all results
        aggregated_evidence = []
        for result in results:
            if result.highlighted_evidence:
                aggregated_evidence.extend(result.highlighted_evidence)
        
        logger.info(f"Aggregated {len(aggregated_evidence)} evidence items from {len(results)} simple merge results")
        
        return EvaluationResult(
            criterion_name=criterion_name,
            verdict=final_verdict,
            reasoning=reasoning,
            confidence_score=avg_confidence,
            aggregated_step_summary=f"Merged {len(results)} {granularity.value} evaluations",
            used_granularity=granularity,
            highlighted_evidence=aggregated_evidence
        )
    
    def _build_raw_context(
        self,
        aggregated_steps: AggregatedSteps,
        all_steps: Optional[List[Dict[str, Any]]],
        step_map: Dict[str, Any]
    ) -> str:
        """Build raw detailed context from actual step data based on granularity level.

        The detailed behavior by granularity:
        - STEP_LEVEL: Return only the full details for the specific step, hiding other steps.
        - PHASE_LEVEL: Return details for steps within the same phase, including a phase summary.
        - GLOBAL_SUMMARY: Return the full execution trace for all steps.

        Args:
            aggregated_steps: The aggregated steps object.
            all_steps: The list of all raw step dictionaries.
            step_map: A mapping of step identifiers to step data.

        Returns:
            A string containing the raw detailed steps data (limited by the granularity level).
        """
        
        granularity = aggregated_steps.granularity
        
        # If no raw steps are provided, return aggregated_content as a fallback
        if not all_steps or len(all_steps) == 0:
            logger.warning("No all_steps provided, using aggregated_content as raw context")
            return aggregated_steps.aggregated_content
        
        try:
            if granularity == Granularity.STEP_LEVEL:
                return self._build_step_level_context(all_steps, step_map)
                    
            elif granularity == Granularity.PHASE_LEVEL:
                return self._build_phase_level_context(all_steps, step_map, aggregated_steps)
                    
            else:  # GLOBAL_SUMMARY or other granularity
                return self._build_global_context(all_steps)
                
        except Exception as e:
            logger.error(f"Error building raw context: {e}")
            logger.info("Falling back to aggregated_content")
            return aggregated_steps.aggregated_content
    
    def _build_step_level_context(
        self,
        all_steps: List[Dict[str, Any]],
        step_map: Dict[str, Any]
    ) -> str:
        """Build context for STEP_LEVEL: only include the specific step being evaluated.
        
        Args:
            all_steps: All execution steps
            step_map: Mapping from aggregated content to original step indices
            
        Returns:
            Raw context containing only the referenced step
        """
        context_parts = []
        
        # STEP_LEVEL: only return the content for the specific step, excluding other steps
        for map_key, step_indices in step_map.items():
            if isinstance(step_indices, list):
                indices_list = step_indices
            else:
                indices_list = [step_indices]
            
            for idx in indices_list:
                try:
                    step_idx = int(idx)
                    if 0 <= step_idx < len(all_steps):
                        step = all_steps[step_idx]
                        context_parts.append(
                            f"Step {step_idx}:\n"
                            f"{json.dumps(step, ensure_ascii=False, indent=2)}"
                        )
                except (ValueError, IndexError, TypeError) as e:
                    logger.warning(f"Failed to retrieve step {idx}: {e}")
        
        if context_parts:
            logger.debug(f"Step-level context includes {len(context_parts)} step(s)")
            return "\n\n".join(context_parts)
        else:
            logger.warning("No steps found for step-level context")
            return ""
    
    def _build_phase_level_context(
        self,
        all_steps: List[Dict[str, Any]],
        step_map: Dict[str, Any],
        aggregated_steps: AggregatedSteps
    ) -> str:
        """Build context for PHASE_LEVEL: only include steps in the referenced phase.
        
        Args:
            all_steps: All execution steps
            step_map: Mapping from phase to step indices
            aggregated_steps: Aggregated steps object containing phase summary
            
        Returns:
            Raw context containing only the phase summary and phase steps
        """
        context_parts = []
        
        # Note: We do NOT include aggregated_steps.aggregated_content here because 
        # it is already included in the prompt as the 'aggregated_steps' variable.
        # We only want the detailed steps here.
        
        # Collect steps that belong only to this phase
        phase_steps = set()
        
        # Priority 1: Try to parse "Relevant steps for evaluation" from content
        # This overrides step_map if present, as it's more specific to the evaluation context
        parsed_indices = []
        if aggregated_steps.aggregated_content:
            import re
            match = re.search(r"Relevant steps for evaluation: \[([\d, ]+)\]", aggregated_steps.aggregated_content)
            if match:
                try:
                    indices_str = match.group(1)
                    parsed_indices = [int(x.strip()) for x in indices_str.split(",") if x.strip().isdigit()]
                    if parsed_indices:
                        phase_steps.update(parsed_indices)
                        logger.info(f"Parsed {len(parsed_indices)} relevant steps from aggregated_content: {parsed_indices}")
                except Exception as e:
                    logger.warning(f"Failed to parse relevant steps from content: {e}")

        # Priority 2: If no relevant steps parsed, use step_map
        if not phase_steps:
            for step_indices in step_map.values():
                if isinstance(step_indices, list):
                    for item in step_indices:
                        if isinstance(item, int):
                            phase_steps.add(item)
                        elif isinstance(item, str) and item.isdigit():
                            phase_steps.add(int(item))
                elif isinstance(step_indices, int):
                    phase_steps.add(step_indices)
                elif isinstance(step_indices, str) and step_indices.isdigit():
                    phase_steps.add(int(step_indices))
        
        # Sort by index
        sorted_indices = sorted(list(phase_steps))
        
        # Only add steps that belong to this phase
        for idx in sorted_indices:
            try:
                step_idx = int(idx)
                if 0 <= step_idx < len(all_steps):
                    step = all_steps[step_idx]
                    
                    # Extract fields for formatted output
                    thinking = step.get("thinking_process") or step.get("thinking") or "N/A"
                    memory = step.get("memory", "N/A")
                    eval_prev = step.get("evaluation_previous_goal", "N/A")
                    action = str(step.get("action", "N/A"))
                    next_goal = step.get("next_goal", "N/A")
                    
                    context_parts.append(
                        f"STEP DATA (The specific step to evaluate):\n"
                        f"Step Index: {step_idx}\n"
                        f"Thinking Process: {thinking}\n"
                        f"Memory: {memory}\n"
                        f"Evaluation of Previous Goal: {eval_prev}\n"
                        f"Action: {action}\n"
                        f"Next Goal: {next_goal}\n\n"
                    )
            except (ValueError, IndexError, TypeError) as e:
                logger.warning(f"Failed to retrieve step {idx}: {e}")
        
        logger.debug(f"Phase-level context includes {len(sorted_indices)} step(s) from this phase only")
        return "".join(context_parts)
    
    def _build_global_context(
        self,
        all_steps: List[Dict[str, Any]]
    ) -> str:
        """Build context for GLOBAL_SUMMARY: include all steps in complete execution trace.
        
        Args:
            all_steps: All execution steps
            
        Returns:
            Raw context containing complete execution trace with all steps
        """
        context_parts = ["=== COMPLETE EXECUTION TRACE ===\n"]
        
        # Add all steps
        for step_idx, step in enumerate(all_steps):
            context_parts.append(
                f"Step {step_idx}:\n"
                f"{json.dumps(step, ensure_ascii=False, indent=2)}\n"
            )
        
        logger.debug(f"Global-level context includes all {len(all_steps)} steps")
        return "".join(context_parts)
    