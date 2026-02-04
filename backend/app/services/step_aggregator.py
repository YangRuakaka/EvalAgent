"""
Service for aggregating and encoding execution steps at different granularity levels.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_core.prompts import PromptTemplate

from ..schemas.judge import Granularity, AggregatedSteps, TaskDecomposition
from .llm_factory import ChatLLMFactory

logger = logging.getLogger(__name__)


class StepAggregatorService:
    """Service to aggregate and encode steps at different granularity levels."""
    
    def __init__(self, llm_factory: ChatLLMFactory):
        """Initialize the StepAggregatorService.
        
        Args:
            llm_factory: Factory for creating LLM clients
        """
        self.llm_factory = llm_factory
        self._setup_prompts()
    
    def _setup_prompts(self) -> None:
        """Setup prompt templates for step encoding and cluster summarization."""
        
        # For STEP_LEVEL: encode individual steps
        self.step_encoding_template = PromptTemplate(
            input_variables=["step_index", "thinking", "next_goal", "action_desc"],
            template="""Encode this agent step concisely:

Step {step_index}:
- Thinking: {thinking}
- Goal: {next_goal}
- Action: {action_desc}

Provide a concise 1-line encoding: [thinking brief] → [action brief] → [expected outcome]
Output only the encoding line, no additional text.""",
        )
        
        # For PHASE_LEVEL: summarize clusters
        self.cluster_summarization_template = PromptTemplate(
            input_variables=["semantic_label", "cluster_steps", "cluster_goal"],
            template="""Summarize this cluster of agent steps:

Cluster: {semantic_label}
Steps:
{cluster_steps}

Expected Goal: {cluster_goal}

Provide a concise 2-3 sentence summary capturing the essence of what this cluster accomplishes.
Output only the summary, no additional text.""",
        )
        
        # For GLOBAL_SUMMARY: overall execution strategy
        self.global_summary_template = PromptTemplate(
            input_variables=["task_name", "all_clusters", "execution_outcome"],
            template="""Summarize the overall execution strategy and approach:

Task: {task_name}
Execution Phases:
{all_clusters}

Final Outcome: {execution_outcome}

Provide a 3-4 sentence high-level summary describing the agent's overall strategy, key decisions, and efficiency.
Output only the summary, no additional text.""",
        )
    
    def aggregate_steps(
        self,
        all_steps: List[Dict[str, Any]],
        granularity: Granularity,
        task_decomposition: Optional[TaskDecomposition] = None,
        task_name: str = "Task",
        execution_outcome: str = "Completed",
        model_name: str = "deepseek-chat"
    ) -> AggregatedSteps:
        """Aggregate and encode steps at a specific granularity level.
        
        Args:
            all_steps: List of original model_output steps
            granularity: Target granularity level
            task_decomposition: Optional task decomposition (needed for PHASE_LEVEL/GLOBAL_SUMMARY)
            task_name: Name of the task
            execution_outcome: Description of task outcome
            model_name: LLM model to use for encoding/summarization
            
        Returns:
            AggregatedSteps with encoded content at the specified granularity
        """
        
        logger.info(f"Aggregating {len(all_steps)} steps at granularity: {granularity}")
        logger.debug(f"All steps type: {type(all_steps)}, first step: {all_steps[0] if all_steps else 'empty'}")
        
        if not all_steps:
            logger.warning(f"No steps provided for aggregation!")
        
        try:
            llm = self.llm_factory.get_langchain_llm(model_name)
            logger.info(f"LLM client created successfully: {type(llm)}")
        except Exception as e:
            logger.error(f"Failed to create LLM client: {e}", exc_info=True)
            raise
        
        if granularity == Granularity.STEP_LEVEL:
            logger.info("Using STEP_LEVEL aggregation")
            return self._aggregate_step_level(all_steps, llm)
        elif granularity == Granularity.PHASE_LEVEL:
            logger.info(f"Using PHASE_LEVEL aggregation. Decomposition available: {task_decomposition is not None}")
            return self._aggregate_phase_level(all_steps, task_decomposition, llm)
        else:  # GLOBAL_SUMMARY
            logger.info("Using GLOBAL_SUMMARY aggregation")
            return self._aggregate_global_summary(
                all_steps, task_decomposition, task_name, execution_outcome, llm
            )
    
    def _aggregate_step_level(
        self,
        all_steps: List[Dict[str, Any]],
        llm: Any
    ) -> AggregatedSteps:
        """Aggregate at STEP_LEVEL: encode each individual step.
        
        Args:
            all_steps: List of execution steps
            llm: LLM client for encoding
            
        Returns:
            AggregatedSteps with step-level encoding
        """
        
        encoded_steps = []
        step_mapping = {}
        
        logger.info(f"Starting _aggregate_step_level with {len(all_steps)} steps")
        logger.info(f"First step sample: {all_steps[0] if all_steps else 'NO STEPS'}")
        
        for i, step in enumerate(all_steps):
            logger.info(f"=== Processing step {i} ===")
            logger.info(f"Step type: {type(step)}")
            logger.info(f"Step value: {step}")
            
            if not isinstance(step, dict):
                logger.warning(f"Step {i} is not a dict, skipping")
                continue
            
            logger.info(f"Step {i} keys: {step.keys()}")
            
            # Safely extract thinking
            thinking_raw = step.get("thinking")
            logger.info(f"Step {i} thinking_raw: {thinking_raw} (type: {type(thinking_raw)})")
            thinking = (thinking_raw if thinking_raw else "")[:150] if isinstance(thinking_raw, (str, type(None))) else str(thinking_raw)[:150]
            
            # Safely extract next_goal
            next_goal_raw = step.get("next_goal")
            logger.info(f"Step {i} next_goal_raw: {next_goal_raw} (type: {type(next_goal_raw)})")
            next_goal = (next_goal_raw if next_goal_raw else "")[:100] if isinstance(next_goal_raw, (str, type(None))) else str(next_goal_raw)[:100]
            
            # Safely extract action
            action = step.get("action", [])
            logger.info(f"Step {i} action: {action} (type: {type(action)})")
            
            logger.debug(f"Step {i}: thinking={thinking[:30] if thinking else 'empty'}, goal={next_goal[:30] if next_goal else 'empty'}, action type={type(action)}")
            
            # Format action description
            if isinstance(action, list) and action:
                if isinstance(action[0], dict):
                    action_type = action[0].get("action_type", "unknown")
                    action_args = action[0].get("coordinate", action[0].get("text", ""))
                    action_desc = f"{action_type}({action_args})"
                else:
                    action_desc = str(action[0])[:100]
            else:
                action_desc = str(action)[:100]
            
            logger.debug(f"Step {i} action_desc: {action_desc}")
            
            # Encode the step (Simplified: No LLM call to save cost/latency)
            # Since this encoding is mostly for logging/debugging and not used in core evaluation logic
            encoded = f"Thinking: {thinking[:50]}... | Action: {action_desc} | Goal: {next_goal[:50]}..."
            logger.debug(f"Step {i} encoded (simplified): {encoded}")
            
            encoded_steps.append(f"Step {i}: {encoded}")
            step_mapping[str(i)] = [i]
        
        aggregated_content = "\n".join(encoded_steps)
        
        return AggregatedSteps(
            granularity=Granularity.STEP_LEVEL,
            aggregated_content=aggregated_content,
            step_mapping=step_mapping,
            summary_metadata={
                "total_steps": len(all_steps),
                "encoding_type": "individual_step_encoding"
            }
        )
    
    def _aggregate_phase_level(
        self,
        all_steps: List[Dict[str, Any]],
        task_decomposition: Optional[TaskDecomposition],
        llm: Any
    ) -> AggregatedSteps:
        """Aggregate at PHASE_LEVEL: return all steps with relevant step indices and phase summaries.
        
        Args:
            all_steps: List of execution steps
            task_decomposition: Task decomposition result (with relevant_step_indices)
            llm: LLM client for summarization
            
        Returns:
            AggregatedSteps with all steps, relevant indices, and phase summaries
        """
        # Check if this is a PhaseDecompositionResult
        has_relevant_indices = hasattr(task_decomposition, 'relevant_step_indices')
        
        if not task_decomposition:
            logger.warning("PHASE_LEVEL requires task decomposition, falling back to STEP_LEVEL")
            return self._aggregate_step_level(all_steps, llm)
        
        # Build aggregated content with relevant step indices highlighted
        phase_content = []
        
        # Add phase summaries if available
        if hasattr(task_decomposition, 'phase_summaries'):
            for phase_id, summary in task_decomposition.phase_summaries.items():
                phase_content.append(f"[{phase_id}] {summary}")
        
        # Add relevant step information if available
        if has_relevant_indices:
            phase_content.append(f"\nRelevant steps for evaluation: {task_decomposition.relevant_step_indices}")
        
        aggregated_content = "\n".join(phase_content) if phase_content else "Phase level aggregation without specific context"
        
        # Build step mapping
        step_mapping = {
            "all_steps": list(range(len(all_steps))),
        }
        
        if has_relevant_indices:
            step_mapping["relevant_steps"] = task_decomposition.relevant_step_indices
        
        if hasattr(task_decomposition, 'phase_clusters'):
            step_mapping["phase_mapping"] = {c.cluster_id: c.step_indices for c in task_decomposition.phase_clusters}
        
        return AggregatedSteps(
            granularity=Granularity.PHASE_LEVEL,
            aggregated_content=aggregated_content,
            step_mapping=step_mapping,
            summary_metadata={
                "total_steps": len(all_steps),
                "relevant_steps_count": len(task_decomposition.relevant_step_indices) if has_relevant_indices else len(all_steps),
                "has_phase_clusters": hasattr(task_decomposition, 'phase_clusters')
            }
        )
    
    def _aggregate_subtask_cluster(
        self,
        all_steps: List[Dict[str, Any]],
        task_decomposition: Optional[TaskDecomposition],
        llm: Any
    ) -> AggregatedSteps:
        """Aggregate at SUBTASK_CLUSTER level: summarize each cluster.
        
        Args:
            all_steps: List of execution steps
            task_decomposition: Task decomposition result
            llm: LLM client for summarization
            
        Returns:
            AggregatedSteps with cluster-level summaries
        """
        
        if not task_decomposition or not task_decomposition.subtask_clusters:
            logger.warning("No task decomposition available, falling back to step level")
            return self._aggregate_step_level(all_steps, llm)
        
        cluster_summaries = []
        step_mapping = {}
        
        for cluster in task_decomposition.subtask_clusters:
            # Collect steps in this cluster
            cluster_steps_list = [all_steps[i] for i in cluster.step_indices if i < len(all_steps)]
            
            # Format cluster steps for LLM
            cluster_steps_text = "\n".join([
                f"  - Step {i}: {step.get('next_goal', 'N/A')[:80]}"
                for i, step in enumerate(cluster_steps_list, start=cluster.step_indices[0])
            ])
            
            # Summarize cluster
            chain = self.cluster_summarization_template | llm
            try:
                invoke_dict = {
                    "semantic_label": cluster.semantic_label,
                    "cluster_steps": cluster_steps_text,
                    "cluster_goal": cluster.cluster_summary
                }
                formatted_prompt = self.cluster_summarization_template.format(**invoke_dict)
                print("\n" + "="*80)
                print(f"[StepAggregatorService._aggregate_subtask_cluster - {cluster.cluster_id}]")
                print("="*80)
                print("[PROMPT SENT TO LLM]:")
                print(formatted_prompt)
                print("="*80)
                
                response = chain.invoke(invoke_dict)
                summary = response.content if hasattr(response, 'content') else str(response)
                summary = summary.strip()
                
                print("[RESPONSE FROM LLM]:")
                print(summary)
                print("="*80 + "\n")
            except Exception as e:
                logger.warning(f"Error summarizing cluster {cluster.cluster_id}: {e}")
                summary = cluster.cluster_summary
            
            summary_line = f"[{cluster.semantic_label}] {summary}"
            cluster_summaries.append(summary_line)
            step_mapping[cluster.cluster_id] = cluster.step_indices
        
        aggregated_content = "\n".join(cluster_summaries)
        
        return AggregatedSteps(
            granularity=Granularity.SUBTASK_CLUSTER,
            aggregated_content=aggregated_content,
            step_mapping=step_mapping,
            summary_metadata={
                "total_clusters": len(task_decomposition.subtask_clusters),
                "total_steps": len(all_steps),
                "cluster_labels": [c.semantic_label for c in task_decomposition.subtask_clusters]
            }
        )
    
    def _aggregate_global_summary(
        self,
        all_steps: List[Dict[str, Any]],
        task_decomposition: Optional[TaskDecomposition],
        task_name: str,
        execution_outcome: str,
        llm: Any
    ) -> AggregatedSteps:
        """Aggregate at GLOBAL_SUMMARY level: overall strategy summary.
        
        Args:
            all_steps: List of execution steps
            task_decomposition: Task decomposition result
            task_name: Name of the task
            execution_outcome: Description of task outcome
            llm: LLM client for summarization
            
        Returns:
            AggregatedSteps with global-level summary
        """
        
        # Format clusters for context
        if task_decomposition and task_decomposition.subtask_clusters:
            clusters_text = "\n".join([
                f"- {c.semantic_label}: {c.cluster_summary}"
                for c in task_decomposition.subtask_clusters
            ])
        else:
            # Fallback: create basic phase description
            mid_point = len(all_steps) // 3
            clusters_text = (
                f"- Initial Phase: Steps 0-{mid_point}\n"
                f"- Middle Phase: Steps {mid_point+1}-{2*mid_point}\n"
                f"- Final Phase: Steps {2*mid_point+1}-{len(all_steps)-1}"
            )
        
        # Generate global summary
        chain = self.global_summary_template | llm
        try:
            invoke_dict = {
                "task_name": task_name,
                "all_clusters": clusters_text,
                "execution_outcome": execution_outcome
            }
            formatted_prompt = self.global_summary_template.format(**invoke_dict)
            print("\n" + "="*80)
            print("[StepAggregatorService._aggregate_global_summary]")
            print("="*80)
            print("[PROMPT SENT TO LLM]:")
            print(formatted_prompt)
            print("="*80)
            
            response = chain.invoke(invoke_dict)
            summary = response.content if hasattr(response, 'content') else str(response)
            summary = summary.strip()
            
            print("[RESPONSE FROM LLM]:")
            print(summary)
            print("="*80 + "\n")
        except Exception as e:
            logger.warning(f"Error generating global summary: {e}")
            summary = f"Agent executed task '{task_name}' with {len(all_steps)} steps, resulting in: {execution_outcome}"
        
        aggregated_content = f"Overall Strategy and Execution:\n{summary}"
        
        return AggregatedSteps(
            granularity=Granularity.GLOBAL_SUMMARY,
            aggregated_content=aggregated_content,
            step_mapping={"all_steps": list(range(len(all_steps)))},
            summary_metadata={
                "total_steps": len(all_steps),
                "summary_type": "global_strategy",
                "execution_outcome": execution_outcome
            }
        )
