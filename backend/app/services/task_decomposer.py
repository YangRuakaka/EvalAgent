"""
Service for decomposing agent execution steps into semantic clusters.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from hashlib import md5

from langchain_core.prompts import PromptTemplate

from ..schemas.judge import TaskDecomposition, StepCluster, PhaseDecompositionResult
from ..schemas.browser_agent import BrowserAgentTask
from .llm_factory import ChatLLMFactory

logger = logging.getLogger(__name__)


class TaskDecomposerService:
    """Service to decompose agent execution into semantic step clusters."""
    
    # Cache for decompositions: key = f"{task_name}_{task_url_hash}"
    _decomposition_cache: Dict[str, TaskDecomposition] = {}
    
    def __init__(self, llm_factory: ChatLLMFactory):
        """Initialize the TaskDecomposerService.
        
        Args:
            llm_factory: Factory for creating LLM clients
        """
        self.llm_factory = llm_factory
        self._setup_decomposition_prompt()
    
    def _setup_decomposition_prompt(self) -> None:
        """Setup the few-shot prompt template for task decomposition."""
        
        examples = """Example 1: E-commerce shopping task
Task: Buy milk from supermarket
Steps summary:
- Step 0: User thinks about the task, visits supermarket website
- Step 1: User searches for milk products
- Step 2: User filters by price and reviews milk options
- Step 3: User selects a milk product and reads description
- Step 4: User adds milk to cart
- Step 5: User proceeds to checkout
- Step 6: User enters payment details
- Step 7: User confirms order

Clusters:
1. cluster_0 (Initial Exploration): Steps [0] - "Initial page exploration and search preparation"
2. cluster_1 (Product Discovery): Steps [1-3] - "Searching and evaluating milk options"
3. cluster_2 (Purchase Execution): Steps [4-7] - "Adding to cart, checkout, and payment"

Example 2: Information research task
Task: Compare smartphone prices
Steps summary:
- Step 0: User visits first phone comparison site
- Step 1: User searches for iPhone 15
- Step 2: User notes the price and specs
- Step 3: User navigates to Amazon
- Step 4: User searches for iPhone 15 on Amazon
- Step 5: User notes the price
- Step 6: User decides based on price difference
- Step 7: User makes purchase decision

Clusters:
1. cluster_0 (Information Gathering): Steps [0-2] - "Gathering information from first source"
2. cluster_1 (Comparison): Steps [3-5] - "Comparing prices across multiple sources"
3. cluster_2 (Decision Making): Steps [6-7] - "Making final purchase decision"
"""
        
        self.decomposition_template = PromptTemplate(
            input_variables=["task_name", "task_url", "steps_text", "criterion_context"],
            template="""You are an expert task analyst. Your job is to decompose agent execution steps into semantic clusters - groups of related steps that accomplish a specific sub-goal.

""" + examples + """

Now analyze the following task:

Task Name: {task_name}
Task URL: {task_url}

{criterion_context}

Agent execution steps:
{steps_text}

Please analyze these steps and create semantic clusters. For each cluster:
1. Assign a cluster_id (e.g., cluster_0, cluster_1)
2. Provide a semantic_label (e.g., "Information Search", "Decision Making")
3. List the step indices included (as a Python list, e.g., [0, 1, 2])
4. Write a concise 1-2 sentence cluster_summary
5. Identify any key_decisions in this cluster
6. Identify dependencies on other clusters (as a list of cluster_ids)
7. If a criterion is provided, identify which clusters are MOST RELEVANT to that criterion (list their cluster_ids)

Output format: JSON object with structure {{"clusters": [{{"cluster_id": "...", "semantic_label": "...", "step_indices": [...], "cluster_summary": "...", "key_decisions": [...], "dependencies": [...], "relevant_to_criterion": true/false}}...], "relevant_cluster_ids": ["cluster_0", "cluster_2"]}}

Ensure:
- Clusters are logically ordered and non-overlapping
- Each step is assigned to exactly one cluster
- Dependencies reflect the actual causal flow
- Summaries are concise and descriptive
- key_decisions are specific to important choices made in that cluster
- If a criterion is provided, mark clusters with "relevant_to_criterion": true for those highly relevant to that criterion""",
        )
        
        # Setup phase-level decomposition prompt that returns relevant step indices
        self.phase_decomposition_template = PromptTemplate(
            input_variables=["task_name", "task_url", "steps_text", "criterion_title", "criterion_assertion"],
            template="""You are an expert task analyst. Your job is to identify which steps in an agent's execution are most relevant to evaluating a specific criterion.

For the given criterion, you should:
1. Identify semantic phases in the agent's execution
2. For each phase, determine if it's RELEVANT to the criterion (relates to the assertion being tested)
3. Output the indices of steps that belong to relevant phases
4. Provide a summary for each relevant phase

IMPORTANT: Return ALL steps in your response, but identify which ones are relevant. The evaluator will then examine the relevant steps in detail.

Task Name: {task_name}
Task URL: {task_url}

Criterion to Evaluate:
Title: {criterion_title}
Assertion: {criterion_assertion}

Agent execution steps:
{steps_text}

For each phase/cluster you identify:
1. Assign a phase_id (e.g., phase_0, phase_1)
2. Provide a semantic_label (e.g., "Information Search", "Decision Making")
3. List ALL step indices in this phase (as a Python list, e.g., [0, 1, 2])
4. Write a concise 1-2 sentence phase_summary
5. Mark as relevant_to_criterion: true/false

Output ONLY a JSON object with this structure:
{{
    "phases": [
        {{
            "phase_id": "phase_0",
            "semantic_label": "...",
            "step_indices": [...],
            "phase_summary": "...",
            "relevant_to_criterion": true/false
        }},
        ...
    ],
    "relevant_phase_ids": ["phase_0", "phase_2"],
    "evaluation_focus": "Brief explanation of which phases are most important for evaluating this criterion"
}}

Ensure:
- All steps are assigned to exactly one phase
- Phases are ordered logically
- Relevant phases are correctly identified based on the criterion assertion
- Summaries are concise""",
        )
    
    def decompose_execution_steps(
        self,
        task: BrowserAgentTask,
        all_steps: List[Dict[str, Any]],
        run_metadata: Optional[Dict[str, Any]] = None,
        criterion: Optional[Dict[str, str]] = None,
        model_name: str = "gpt-4o-mini"  # Optimized: faster/cheaper for clustering
    ) -> TaskDecomposition:
        """Decompose execution steps into semantic clusters.
        
        Args:
            task: The BrowserAgentTask definition
            all_steps: List of model_output steps from agent execution
            run_metadata: Optional metadata about the run
            criterion: Optional criterion to guide decomposition (name, description)
            model_name: LLM model name to use for decomposition
            
        Returns:
            TaskDecomposition with semantic clusters
        """
        
        # Check cache first
        cache_key = self._get_cache_key(task.name, task.url, criterion)
        if cache_key in self._decomposition_cache:
            logger.info(f"Using cached decomposition for task: {task.name}")
            return self._decomposition_cache[cache_key]
        
        # Convert steps to text representation
        steps_text = self._format_steps_for_analysis(all_steps)
        
        # Prepare criterion context
        criterion_context = ""
        if criterion:
            criterion_context = f"Focus on decomposing the task with respect to this criterion:\nName: {criterion.get('title', criterion.get('name', ''))}\nDescription: {criterion.get('description', '')}\nAssertion: {criterion.get('assertion', '')}\n"
        
        # Create LLM client
        llm = self.llm_factory.get_langchain_llm(model_name)
        
        # Create and run the decomposition chain
        chain = self.decomposition_template | llm
        
        logger.info(f"Decomposing task: {task.name} with {len(all_steps)} steps. Criterion: {criterion.get('title') if criterion else 'None'}")
        
        formatted_prompt = self.decomposition_template.format(
            task_name=task.name,
            task_url=task.url,
            steps_text=steps_text,
            criterion_context=criterion_context
        )
        print("\n" + "="*80)
        print("[TaskDecomposerService.decompose_execution_steps]")
        print("="*80)
        print("[PROMPT SENT TO LLM]:")
        print(formatted_prompt)
        print("="*80)
        
        response = chain.invoke({
            "task_name": task.name,
            "task_url": task.url,
            "steps_text": steps_text,
            "criterion_context": criterion_context
        })
        
        response_text = response.content if hasattr(response, "content") else str(response)
        print("[RESPONSE FROM LLM]:")
        print(response_text)
        print("="*80 + "\n")
        logger.debug("LLM decomposition response: %s", response_text)
        
        # Parse response
        decomposition = self._parse_decomposition_response(
            response.content if hasattr(response, 'content') else str(response),
            task.name,
            len(all_steps)
        )
        
        # Cache the result
        self._decomposition_cache[cache_key] = decomposition
        
        logger.info(f"Task decomposition created {len(decomposition.subtask_clusters)} clusters")
        return decomposition
    
    def decompose_for_phase_evaluation(
        self,
        task: BrowserAgentTask,
        all_steps: List[Dict[str, Any]],
        criterion_title: str,
        criterion_assertion: str,
        model_name: str = "gpt-4o-mini"  # Optimized: faster/cheaper for clustering
    ) -> PhaseDecompositionResult:
        """Decompose execution steps for phase-level criterion evaluation.
        
        Returns relevant step indices and phase summaries for LLM evaluation.
        Does NOT filter steps - returns all steps along with relevant step indices.
        
        Args:
            task: The BrowserAgentTask definition
            all_steps: List of model_output steps from agent execution
            criterion_title: Title of the criterion being evaluated
            criterion_assertion: Assertion of the criterion
            model_name: LLM model name to use for decomposition
            
        Returns:
            PhaseDecompositionResult with phase clusters, all steps, relevant step indices, and summaries
        """
        
        logger.info(f"Phase decomposition for criterion: {criterion_title}")
        
        # Convert steps to text representation
        steps_text = self._format_steps_for_analysis(all_steps)
        
        # Create LLM client
        llm = self.llm_factory.get_langchain_llm(model_name)
        
        # Create and run the phase decomposition chain
        chain = self.phase_decomposition_template | llm
        
        try:
            formatted_prompt = self.phase_decomposition_template.format(
                task_name=task.name,
                task_url=task.url,
                steps_text=steps_text,
                criterion_title=criterion_title,
                criterion_assertion=criterion_assertion
            )
            print("\n" + "="*80)
            print("[TaskDecomposerService.decompose_for_phase_evaluation]")
            print("="*80)
            print("[PROMPT SENT TO LLM]:")
            print(formatted_prompt)
            print("="*80)
            
            response = chain.invoke({
                "task_name": task.name,
                "task_url": task.url,
                "steps_text": steps_text,
                "criterion_title": criterion_title,
                "criterion_assertion": criterion_assertion
            })
            
            if response is None:
                logger.error("LLM chain returned None response")
                return self._create_default_phase_decomposition(all_steps)
            
            response_text = response.content if hasattr(response, "content") else str(response)
            if response_text is None:
                logger.error("Response content is None")
                return self._create_default_phase_decomposition(all_steps)
            
            print("[RESPONSE FROM LLM]:")
            print(response_text)
            print("="*80 + "\n")
            logger.debug("LLM phase decomposition response: %s", response_text)
            
            # Parse response
            result = self._parse_phase_decomposition_response(
                response_text,
                all_steps
            )
            
            if result is None:
                logger.error("Phase decomposition parsing returned None")
                return self._create_default_phase_decomposition(all_steps)
            
            logger.info(f"Phase decomposition identified {len(result.relevant_step_indices)} relevant steps out of {len(all_steps)}")
            return result
        except Exception as e:
            logger.error(f"Phase decomposition chain invocation failed: {e}", exc_info=True)
            return self._create_default_phase_decomposition(all_steps)
    
    def _parse_phase_decomposition_response(
        self,
        response_text: str,
        all_steps: List[Dict[str, Any]]
    ) -> PhaseDecompositionResult:
        """Parse phase decomposition LLM response.
        
        Args:
            response_text: Raw LLM response
            all_steps: All execution steps
            
        Returns:
            PhaseDecompositionResult with phases, relevant indices, and summaries
        """
        try:
            if response_text is None or not response_text:
                logger.warning("Empty or None phase decomposition response")
                return self._create_default_phase_decomposition(all_steps)

            # Extract JSON from response (first/last braces)
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start == -1 or json_end == 0:
                logger.warning("Could not find JSON in phase decomposition response")
                return self._create_default_phase_decomposition(all_steps)

            json_str = response_text[json_start:json_end]
            response_data = json.loads(json_str)

            if not isinstance(response_data, dict):
                logger.warning("Parsed phase decomposition JSON is not an object")
                return self._create_default_phase_decomposition(all_steps)

            phases_data = response_data.get("phases") or []
            relevant_phase_ids = response_data.get("relevant_phase_ids") or []

            if not isinstance(phases_data, list):
                logger.warning("'phases' field is not a list in phase decomposition response")
                return self._create_default_phase_decomposition(all_steps)

            # Convert to StepCluster objects
            phase_clusters: List[StepCluster] = []
            phase_summaries: Dict[str, str] = {}
            relevant_step_indices = set()

            for idx, phase_data in enumerate(phases_data):
                if not isinstance(phase_data, dict):
                    logger.warning("Skipping non-dict phase entry at index %d", idx)
                    continue

                phase_id = phase_data.get("phase_id", f"phase_{len(phase_clusters)}")

                # Ensure step_indices is a list of ints; coerce if necessary
                raw_indices = phase_data.get("step_indices")
                if raw_indices is None:
                    step_indices: List[int] = []
                elif isinstance(raw_indices, list):
                    # filter and coerce to ints where possible
                    step_indices = []
                    for s in raw_indices:
                        try:
                            step_indices.append(int(s))
                        except Exception:
                            continue
                elif isinstance(raw_indices, str):
                    # try to parse stringified list
                    try:
                        parsed = json.loads(raw_indices)
                        if isinstance(parsed, list):
                            step_indices = [int(s) for s in parsed if isinstance(s, (int, str)) and str(s).isdigit()]
                        else:
                            step_indices = []
                    except Exception:
                        step_indices = []
                else:
                    step_indices = []

                cluster = StepCluster(
                    cluster_id=phase_id,
                    semantic_label=phase_data.get("semantic_label", "Unknown Phase"),
                    step_indices=step_indices,
                    cluster_summary=phase_data.get("phase_summary", ""),
                    key_decisions=[],
                    dependencies=[]
                )

                phase_clusters.append(cluster)
                phase_summaries[phase_id] = phase_data.get("phase_summary", "")

                # If this phase is relevant, add its steps to relevant_step_indices
                try:
                    if phase_data.get("relevant_to_criterion", False) or phase_id in relevant_phase_ids:
                        relevant_step_indices.update(step_indices)
                except Exception:
                    # Defensive: if relevant flag malformed, skip
                    pass

            result = PhaseDecompositionResult(
                phase_clusters=phase_clusters,
                all_steps=all_steps,
                relevant_step_indices=sorted(list(relevant_step_indices)),
                phase_summaries=phase_summaries,
                total_steps=len(all_steps)
            )
            logger.debug(f"Successfully parsed phase decomposition: {len(phase_clusters)} phases, {len(relevant_step_indices)} relevant steps")
            return result

        except Exception as e:
            logger.error(f"Failed to parse phase decomposition response: {e}", exc_info=True)
            logger.debug("Phase decomposition response text: %s", response_text)
            return self._create_default_phase_decomposition(all_steps)
    
    def _create_default_phase_decomposition(
        self,
        all_steps: List[Dict[str, Any]]
    ) -> PhaseDecompositionResult:
        """Create a default phase decomposition when parsing fails.
        
        Args:
            all_steps: All execution steps
            
        Returns:
            Default PhaseDecompositionResult (all steps as relevant)
        """
        
        cluster = StepCluster(
            cluster_id="phase_0",
            semantic_label="Complete Task Execution",
            step_indices=list(range(len(all_steps))),
            cluster_summary=f"Complete execution with {len(all_steps)} steps",
            key_decisions=[],
            dependencies=[]
        )
        
        return PhaseDecompositionResult(
            phase_clusters=[cluster],
            all_steps=all_steps,
            relevant_step_indices=list(range(len(all_steps))),
            phase_summaries={"phase_0": f"Complete execution with {len(all_steps)} steps"},
            total_steps=len(all_steps)
        )
    
    def _format_steps_for_analysis(self, steps: List[Dict[str, Any]]) -> str:
        """Format execution steps for LLM analysis.
        
        Args:
            steps: List of model_output steps
            
        Returns:
            Formatted string representation of steps
        """
        
        lines = []
        for i, step in enumerate(steps):
            # Safely get and convert to string before truncating
            thinking = str(step.get("thinking", "") or "")[:100]
            next_goal = str(step.get("next_goal", "") or "")[:100]
            action = step.get("action", [])
            
            if isinstance(action, list) and action:
                action_str = action[0].get("action_type", "unknown") if isinstance(action[0], dict) else str(action[0])
            else:
                action_str = str(action or "")[:100]
            
            lines.append(
                f"Step {i}: thinking='{thinking}' | goal='{next_goal}' | action='{action_str}'"
            )
        
        return "\n".join(lines)
    
    def _parse_decomposition_response(
        self,
        response_text: str,
        task_name: str,
        total_steps: int
    ) -> TaskDecomposition:
        """Parse LLM response into TaskDecomposition object.
        
        Args:
            response_text: Raw LLM response
            task_name: Name of the task
            total_steps: Total number of execution steps
            
        Returns:
            TaskDecomposition object
        """
        
        try:
            # Try to extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("Could not find JSON in response, creating default decomposition")
                return self._create_default_decomposition(task_name, total_steps)
            
            json_str = response_text[json_start:json_end]
            response_data = json.loads(json_str)
            
            clusters_data = response_data.get("clusters", [])
            
            # Convert to StepCluster objects
            clusters = []
            for cluster_data in clusters_data:
                cluster = StepCluster(
                    cluster_id=cluster_data.get("cluster_id", f"cluster_{len(clusters)}"),
                    semantic_label=cluster_data.get("semantic_label", "Unknown"),
                    step_indices=cluster_data.get("step_indices", []),
                    cluster_summary=cluster_data.get("cluster_summary", ""),
                    key_decisions=cluster_data.get("key_decisions", []),
                    dependencies=cluster_data.get("dependencies", [])
                )
                clusters.append(cluster)
            
            return TaskDecomposition(
                task_name=task_name,
                subtask_clusters=clusters,
                total_steps=total_steps,
                decomposition_timestamp=datetime.utcnow()
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from LLM response: {e}")
            return self._create_default_decomposition(task_name, total_steps)
    
    def _create_default_decomposition(
        self,
        task_name: str,
        total_steps: int
    ) -> TaskDecomposition:
        """Create a default decomposition when parsing fails.
        
        Args:
            task_name: Name of the task
            total_steps: Total number of steps
            
        Returns:
            Default TaskDecomposition (all steps in single cluster)
        """
        
        cluster = StepCluster(
            cluster_id="cluster_0",
            semantic_label="Task Execution",
            step_indices=list(range(total_steps)),
            cluster_summary=f"Complete task execution with {total_steps} steps",
            key_decisions=[],
            dependencies=[]
        )
        
        return TaskDecomposition(
            task_name=task_name,
            subtask_clusters=[cluster],
            total_steps=total_steps,
            decomposition_timestamp=datetime.utcnow()
        )
    
    def _get_cache_key(self, task_name: str, task_url: str, criterion: Optional[Dict[str, str]] = None) -> str:
        """Generate a cache key for a task.
        
        Args:
            task_name: Name of the task
            task_url: URL of the task
            criterion: Optional criterion dict
            
        Returns:
            Cache key string
        """
        
        raw_key = f"{task_name}_{task_url}"
        if criterion:
            raw_key += f"_{criterion.get('title', criterion.get('name', ''))}"
            
        return md5(raw_key.encode()).hexdigest()
    
    def clear_cache(self) -> None:
        """Clear the decomposition cache."""
        self._decomposition_cache.clear()
        logger.info("Decomposition cache cleared")
