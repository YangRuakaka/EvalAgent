"""
Service for analyzing which granularity level is needed for a criterion.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, List, TYPE_CHECKING
from langchain_core.prompts import PromptTemplate

from ..schemas.judge import Granularity, GranularityRequirement
from .llm_factory import ChatLLMFactory

if TYPE_CHECKING:
    from ..schemas.judge import TaskDecomposition

logger = logging.getLogger(__name__)


class GranularityAnalyzerService:
    """Service to determine required granularity for evaluation criteria."""
    
    def __init__(self, llm_factory: ChatLLMFactory):
        """Initialize the GranularityAnalyzerService.
        
        Args:
            llm_factory: Factory for creating LLM clients
        """
        self.llm_factory = llm_factory
        self._setup_analysis_prompt()
    
    def _setup_analysis_prompt(self) -> None:
        """Setup the prompt template for granularity analysis."""
    
        self.analysis_template = PromptTemplate(
            input_variables=["criterion_name", "criterion_assertion", "task_name", "available_granularities", "trace_summary"],
            template="""You are an expert in task analysis and evaluation methodology. Your job is to select the appropriate evaluation granularity for a given criterion and explain why that granularity is required.

Available granularity levels:
{available_granularities}

Granularity definitions (use these exact meanings when choosing):
- STEP_LEVEL: Evaluate specific steps individually. Use provided trace summary to identify which steps are relevant to this criterion.
- PHASE_LEVEL: Evaluate a sequence or phase of steps where contextual relationships between steps matter.
- GLOBAL_SUMMARY: Evaluate the entire trajectory using full-context.

Now analyze the following criterion:

Criterion Name: {criterion_name}
Task Name: {task_name}
Criterion Assertion: {criterion_assertion}

Trace Summary:
{trace_summary}

Decide:
1. Which ONE granularity is most appropriate.
2. Provide a rationale.
3. If STEP_LEVEL is selected, you MUST identify which specific steps (by index) need to be evaluated based on the Trace Summary. List them in 'target_step_indices'. If the criterion applies to the whole execution logic but still step-by-step, select the relevant steps.

Important: Output **ONLY** a single JSON object. Format exactly as:
{{"required_granularity": "GRANULARITY_NAME", "rationale": "...", "target_step_indices": [0, 1, 5]}}""",
    )

    
    def analyze_criterion_granularity(
        self,
        criterion_name: str,
        criterion_assertion: str,
        task_name: str,
        model_name: str = "gpt-4o-mini",  # Optimized: faster/cheaper for classification
        allowed_granularities: Optional[List[Granularity]] = None,
        task_decomposition: Optional[TaskDecomposition] = None
    ) -> GranularityRequirement:
        """Analyze and determine the required granularity for a criterion.
        
        Args:
            criterion_name: Name of the criterion
            criterion_assertion: How to verify/assert this criterion
            task_name: Name of the task context
            model_name: LLM model to use for analysis
            allowed_granularities: Optional list of allowed granularities. If None, all are allowed.
            task_decomposition: Optional task decomposition to help identify relevant clusters
            
        Returns:
            GranularityRequirement specifying the recommended granularity and target clusters
        """
        
        logger.info(f"Analyzing granularity for criterion: {criterion_name}")
        
        # Default to all if not specified
        if allowed_granularities is None:
            allowed_granularities = [Granularity.STEP_LEVEL, Granularity.PHASE_LEVEL, Granularity.GLOBAL_SUMMARY]
            
        # Format available granularities string
        available_str = ""
        for i, g in enumerate(allowed_granularities, 1):
            desc = ""
            if g == Granularity.STEP_LEVEL:
                desc = "Evaluate individual agent steps (finest granularity, detailed)"
            elif g == Granularity.PHASE_LEVEL:
                desc = "Evaluate semantically grouped clusters of steps (medium granularity, balanced)"
            elif g == Granularity.GLOBAL_SUMMARY:
                desc = "Evaluate overall task execution strategy and outcomes (coarsest granularity, high-level)"
            available_str += f"{i}. {g.name} - {desc}\n"
        
        # Prepare trace summary
        trace_summary = "No trace info available."
        if task_decomposition and task_decomposition.subtask_clusters:
            lines = []
            for cluster in task_decomposition.subtask_clusters:
                indices = sorted(cluster.step_indices)
                if indices:
                    lines.append(f"- Steps {indices[0]}-{indices[-1]} [{cluster.semantic_label}]: {cluster.cluster_summary}")
            trace_summary = "\n".join(lines)

        # Use LLM-based analysis
        logger.info(f"Using LLM to analyze granularity for: {criterion_name}")
        llm = self.llm_factory.get_langchain_llm(model_name)
        chain = self.analysis_template | llm

        formatted_prompt = self.analysis_template.format(
            criterion_name=criterion_name,
            available_granularities=available_str,
            criterion_assertion=criterion_assertion,
            task_name=task_name,
            trace_summary=trace_summary
        )
        print("\n" + "="*80)
        print("[GranularityAnalyzerService.analyze_criterion_granularity]")
        print("="*80)
        print("[PROMPT SENT TO LLM]:")
        print(formatted_prompt)
        print("="*80)
        
        response = chain.invoke({
            "criterion_name": criterion_name,
            "available_granularities": available_str,
            "criterion_assertion": criterion_assertion,
            "task_name": task_name,
            "trace_summary": trace_summary
        })
        
        response_text = response.content if hasattr(response, 'content') else str(response)
        print("[RESPONSE FROM LLM]:")
        print(response_text)
        print("="*80 + "\n")
        
        requirement = self._parse_granularity_response(
            response_text,
            criterion_name,
            task_decomposition
        )
        
        return requirement
    
    def _parse_granularity_response(
        self,
        response_text: str,
        criterion_name: str,
        task_decomposition: Optional[TaskDecomposition] = None
    ) -> GranularityRequirement:
        """Parse LLM response into GranularityRequirement.
        
        Args:
            response_text: Raw LLM response
            criterion_name: Name of the criterion
            task_decomposition: Optional task decomposition for identifying relevant clusters
            
        Returns:
            GranularityRequirement object
        """
        
        try:
            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("Could not find JSON in response")
                return self._create_default_requirement(criterion_name)
            
            json_str = response_text[json_start:json_end]
            response_data = json.loads(json_str)
            
            granularity_str = response_data.get("required_granularity", "PHASE_LEVEL")
            rationale = response_data.get("rationale", "")
            target_step_indices = response_data.get("target_step_indices", [])
            
            # Map string to enum
            if granularity_str == "STEP_LEVEL":
                granularity = Granularity.STEP_LEVEL
            elif granularity_str == "GLOBAL_SUMMARY":
                granularity = Granularity.GLOBAL_SUMMARY
            else:
                granularity = Granularity.PHASE_LEVEL
            
            # For PHASE_LEVEL, try to detect relevant clusters from the criterion
            target_clusters = []
            if granularity == Granularity.PHASE_LEVEL and task_decomposition:
                target_clusters = self._identify_relevant_clusters(
                    criterion_name,
                    task_decomposition
                )
            
            requirement = GranularityRequirement(
                criterion_name=criterion_name,
                required_granularity=granularity,
                rationale=rationale,
                target_cluster_indices=target_clusters,
                target_step_indices=target_step_indices
            )
            
            logger.info(f"Granularity requirement for '{criterion_name}': {granularity.value}, target clusters: {target_clusters}, target steps: {target_step_indices}")
            
            return requirement
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse granularity JSON: {e}")
            return self._create_default_requirement(criterion_name)
    
    def _identify_relevant_clusters(
        self,
        criterion_name: str,
        task_decomposition: TaskDecomposition
    ) -> List[int]:
        """Try to identify which clusters are relevant for this criterion.
        
        This is a heuristic approach. For now, returns all clusters.
        In the future, this could use LLM or semantic matching to identify
        only the relevant clusters.
        
        Args:
            criterion_name: Name of the criterion
            task_decomposition: The task decomposition with clusters
            
        Returns:
            List of cluster indices that are relevant (empty list means all)
        """
        
        # For now, return empty list to indicate all clusters
        # In the future, you could add more sophisticated logic here:
        # - Parse criterion keywords to match cluster descriptions
        # - Use LLM to match criterion to clusters
        # - Allow users to explicitly specify clusters
        
        logger.debug(f"Identified clusters for '{criterion_name}': all clusters (total: {len(task_decomposition.subtask_clusters)})")
        
        return []  # Empty list means evaluate all clusters
    
    def _create_default_requirement(self, criterion_name: str) -> GranularityRequirement:
        """Create a default GranularityRequirement when parsing fails.
        
        Args:
            criterion_name: Name of the criterion
            
        Returns:
            Default GranularityRequirement (PHASE_LEVEL)
        """
        
        return GranularityRequirement(
            criterion_name=criterion_name,
            required_granularity=Granularity.PHASE_LEVEL,
            rationale="Default granularity chosen. Use PHASE_LEVEL for balanced evaluation."
        )
