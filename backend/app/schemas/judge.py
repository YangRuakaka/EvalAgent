"""
Pydantic schemas for Agent as a Judge functionality.
Defines data models for task decomposition, granularity analysis, and evaluation.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Granularity(str, Enum):
    """Enumeration of evaluation granularity levels."""
    
    STEP_LEVEL = "step_level"
    """Evaluate individual agent steps (finest granularity)."""
    
    PHASE_LEVEL = "phase_level"
    """Evaluate aggregated phase clusters (medium granularity)."""
    
    GLOBAL_SUMMARY = "global_summary"
    """Evaluate overall task execution strategy (coarsest granularity)."""


class StepCluster(BaseModel):
    """Represents a semantically grouped cluster of execution steps."""
    
    cluster_id: str = Field(..., description="Unique identifier for this cluster")
    semantic_label: str = Field(..., description="Semantic label for the cluster (e.g., 'Information Search')")
    step_indices: List[int] = Field(..., description="Indices of original steps included in this cluster")
    cluster_summary: str = Field(..., description="LLM-generated summary of the cluster (1-2 sentences)")
    key_decisions: List[str] = Field(default_factory=list, description="Key decision points in this cluster")
    dependencies: List[str] = Field(default_factory=list, description="IDs of upstream clusters this depends on")
    
    model_config = ConfigDict(extra="allow")


class TaskDecomposition(BaseModel):
    """Result of task decomposition: semantic grouping of execution steps."""
    
    task_name: str = Field(..., description="Name of the task")
    subtask_clusters: List[StepCluster] = Field(..., description="List of semantically grouped step clusters")
    total_steps: int = Field(..., description="Total number of original steps")
    decomposition_timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "task_name": "Book a flight",
                "subtask_clusters": [
                    {
                        "cluster_id": "cluster_1",
                        "semantic_label": "Search for flights",
                        "step_indices": [1, 2, 3],
                        "cluster_summary": "User navigated to the travel site and entered flight details.",
                        "key_decisions": ["Selected round-trip", "Entered dates"],
                        "dependencies": []
                    }
                ],
                "total_steps": 3,
                "decomposition_timestamp": "2023-10-27T10:00:00Z"
            }
        }
    )


class PhaseDecompositionResult(BaseModel):
    """Result of phase-level decomposition for criterion evaluation."""
    
    phase_clusters: List[StepCluster] = Field(..., description="List of identified phase clusters")
    all_steps: List[Dict[str, Any]] = Field(..., description="All original steps (not filtered)")
    relevant_step_indices: List[int] = Field(..., description="Indices of steps relevant to the criterion")
    phase_summaries: Dict[str, str] = Field(default_factory=dict, description="Mapping of cluster_id to summary text")
    total_steps: int = Field(..., description="Total number of steps in the run")
    
    model_config = ConfigDict(extra="allow")


class GranularityRequirement(BaseModel):
    """Requirement specification: which granularity level is needed for a criterion."""
    
    criterion_name: str = Field(..., description="Name of the criterion")
    required_granularity: Granularity = Field(..., description="Minimum required granularity level")
    rationale: str = Field(..., description="Explanation of why this granularity is needed")
    target_cluster_indices: List[int] = Field(default_factory=list, description="For PHASE_LEVEL, specific cluster indices to evaluate. Empty list means all clusters.")
    target_step_indices: List[int] = Field(default_factory=list, description="For STEP_LEVEL, specific step indices to evaluate. Empty list means all steps.")
    
    model_config = ConfigDict(extra="allow")


class AggregatedSteps(BaseModel):
    """Aggregated and encoded steps at a specific granularity level."""
    
    granularity: Granularity = Field(..., description="The granularity level of this aggregation")
    aggregated_content: str = Field(..., description="Textual representation of aggregated steps")
    step_mapping: Dict[str, Any] = Field(default_factory=dict, description="Mapping between aggregated and original step indices")
    summary_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata: step count, milestones, etc.")
    
    model_config = ConfigDict(extra="allow")


class AgentStepField(str, Enum):
    """Fields in the agent step that can be highlighted."""
    EVALUATION = "Evaluation"
    MEMORY = "Memory"
    THINKING_PROCESS = "Thinking Process"
    NEXT_GOAL = "Next Goal"
    ACTION = "Action"


class EvaluateStatus(str, Enum):
    """Status of the evaluation."""
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class EvidenceCitation(BaseModel):
    """Citation for highlighted evidence in the agent's execution."""
    step_index: int = Field(..., description="Index of the step containing the evidence")
    source_field: AgentStepField = Field(..., description="Field in the step containing the evidence")
    highlighted_text: str = Field(..., description="The specific text to highlight")
    reasoning: Optional[str] = Field(None, description="Why this evidence is relevant")
    verdict: Optional[EvaluateStatus] = Field(None, description="Evaluation verdict for this specific step")


class StepEvaluationDetail(BaseModel):
    """Detailed evaluation for a specific granularity level."""
    granularity: Granularity = Field(..., description="Granularity level of this evaluation detail")
    evaluateStatus: EvaluateStatus = Field(..., description="Pass/Fail status")
    reasoning: str = Field(..., description="Reasoning for the status")
    highlighted_evidence: List[EvidenceCitation] = Field(default_factory=list, description="Evidence supporting the evaluation")
    confidenceScore: float = Field(..., ge=0, le=1, description="Confidence score (0-1)")
    steps: List[int] = Field(default_factory=list, description="Indices of steps involved in this evaluation")


class EvaluationResult(BaseModel):
    """Result of evaluating a single criterion against aggregated steps."""
    
    criterion_name: str = Field(..., description="Name of the evaluated criterion")
    verdict: str = Field(..., description="Evaluation verdict: PASS/FAIL/PARTIAL/UNABLE_TO_EVALUATE")
    reasoning: str = Field(..., description="Detailed reasoning and evidence for the verdict")
    confidence_score: float = Field(..., ge=0, le=1, description="Confidence score (0-1)")
    relevant_steps: List[int] = Field(default_factory=list, description="Indices of relevant steps for this evaluation")
    aggregated_step_summary: str = Field(..., description="The aggregated step content that was evaluated")
    used_granularity: Granularity = Field(..., description="Granularity level used for this evaluation")
    supporting_evidence: Optional[str] = Field(None, description="Specific evidence quotes from the steps")
    highlighted_evidence: List[EvidenceCitation] = Field(default_factory=list, description="Structured evidence for highlighting")
    
    model_config = ConfigDict(extra="allow")


class OverallAssessment(BaseModel):
    """Cross-criterion assessment summary."""
    
    total_criteria: int = Field(..., description="Total number of criteria evaluated")
    passed_count: int = Field(..., description="Number of criteria that passed")
    failed_count: int = Field(..., description="Number of criteria that failed")
    partial_count: int = Field(..., description="Number of partial pass criteria")
    unable_to_evaluate_count: int = Field(..., description="Number of criteria that could not be evaluated")
    average_confidence: float = Field(..., ge=0, le=1, description="Average confidence score across all criteria")
    overall_summary: str = Field(..., description="High-level summary of overall evaluation")
    
    model_config = ConfigDict(extra="allow")


class JudgeEvaluationReport(BaseModel):
    """Complete evaluation report from Agent as a Judge."""
    
    run_id: str = Field(..., description="ID of the agent run being evaluated")
    evaluation_timestamp: datetime = Field(default_factory=datetime.utcnow)
    task_decomposition: TaskDecomposition = Field(..., description="Task decomposition result")
    evaluation_results: List[EvaluationResult] = Field(..., description="Results for each criterion")
    granularity_analysis: List[GranularityRequirement] = Field(..., description="Granularity requirements for each criterion")
    overall_assessment: OverallAssessment = Field(..., description="Cross-criterion overall assessment")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata about the evaluation")
    
    model_config = ConfigDict(extra="allow")


# Request/Response models for API endpoints

class GranularityAnalysisRequest(BaseModel):
    """Request to analyze required granularity for a criterion."""
    
    criterion: Dict[str, str] = Field(
        ...,
        description="Criterion with name, description, assertion fields"
    )
    task_name: str = Field(..., description="Name of the task being evaluated")
    task_url: Optional[str] = Field(None, description="URL of the task")
    
    model_config = ConfigDict(extra="allow")


class GranularityRequirementResponse(BaseModel):
    """Response with granularity analysis result."""
    
    criterion_name: str = Field(..., description="Name of the criterion")
    required_granularity: Granularity = Field(..., description="Recommended granularity level")
    rationale: str = Field(..., description="Reasoning for the granularity choice")
    
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "criterion_name": "Task Completion",
                "required_granularity": "step_level",
                "rationale": "Evaluating task completion requires checking the final step for success confirmation."
            }
        }
    )


class TaskDecompositionRequest(BaseModel):
    """Request to decompose a task's execution steps."""
    
    run_id: str = Field(..., description="ID of the agent run to decompose")
    
    model_config = ConfigDict(extra="allow")


class StepAggregationRequest(BaseModel):
    """Request to aggregate steps at a specific granularity."""
    
    run_id: str = Field(..., description="ID of the agent run")
    granularity: Granularity = Field(..., description="Target granularity level for aggregation")
    
    model_config = ConfigDict(extra="allow")


# New schemas for Experiment Evaluation API

class ExperimentCriterion(BaseModel):
    """Criterion definition for an experiment."""
    title: str = Field(..., description="Title of the criterion")
    assertion: str = Field(..., description="Assertion to verify")
    description: Optional[str] = Field(None, description="Description of the criterion")

    @model_validator(mode='before')
    @classmethod
    def map_name_to_title(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if 'title' not in data and 'name' in data:
                data['title'] = data['name']
        return data

class ExperimentCriterionResult(ExperimentCriterion):
    """Result of evaluating a criterion."""
    granularity: Granularity = Field(..., description="Overall granularity used")
    involved_steps: List[StepEvaluationDetail] = Field(..., description="Detailed evaluations")
    overall_assessment: Optional[EvaluateStatus] = Field(None, description="Overall pass/fail assessment for this criterion")
    overall_reasoning: Optional[str] = Field(None, description="Reasoning for the overall assessment")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="Confidence score for the overall assessment (0-1)")

class ConditionRequest(BaseModel):
    """Request for a single condition within an experiment."""
    conditionID: str = Field(..., description="Condition ID (filename without .json extension)")

class ConditionResult(BaseModel):
    """Result for a single condition within an experiment."""
    conditionID: str = Field(..., description="Condition ID (filename without .json extension)")
    persona: str = Field(..., description="Persona used in this condition")
    value: Optional[str] = Field(None, description="Value orientation of the agent")
    model: str = Field(..., description="Model used in this condition")
    run_index: int = Field(..., description="Index of the run")
    criteria: List[ExperimentCriterionResult] = Field(..., description="Evaluation results for criteria")

class ExperimentEvaluationRequest(BaseModel):
    """Request to evaluate an experiment consisting of multiple conditions."""
    conditions: List[ConditionRequest] = Field(..., description="List of condition IDs to evaluate")
    criteria: List[ExperimentCriterion] = Field(..., description="List of criteria to evaluate for all conditions")

class RankingItem(BaseModel):
    """A single item in the condition ranking."""
    rank: int = Field(..., ge=1, description="Rank position (1-indexed)")
    condition_id: str = Field(..., description="Condition ID")
    overall_assessment: EvaluateStatus = Field(..., description="Overall assessment status")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score (0-1)")
    summary: str = Field(..., description="Brief summary of this condition's performance on the criterion")
    persona: str = Field(..., description="Persona used in this condition")
    value: Optional[str] = Field(None, description="Value orientation of the agent")
    model: str = Field(..., description="Model used in this condition")
    run_index: int = Field(..., description="Run index of this condition")


class ConditionComparison(BaseModel):
    """Comparison of a criterion across multiple conditions."""
    best_condition_id: str = Field(..., description="Condition ID that performed best for this criterion")
    best_condition_rank: int = Field(..., ge=1, description="Rank of the best condition (1-indexed)")
    ranking: List[RankingItem] = Field(..., description="Ordered list of conditions ranked from best to worst")
    ranking_reasoning: str = Field(..., description="Detailed explanation of the ranking and why the best condition excels")
    comparison_summary: str = Field(..., description="Summary of how conditions differ on this criterion")


class CriteriaMultiConditionAssessment(BaseModel):
    """Multi-condition assessment of a criterion across conditions."""
    title: str = Field(..., description="Title of the criterion")
    assertion: str = Field(..., description="Assertion to verify")
    description: Optional[str] = Field(None, description="Description of the criterion")
    granularity: Granularity = Field(..., description="Granularity level used for this criterion")
    condition_comparison: ConditionComparison = Field(..., description="Comparison results across conditions")


class MultiConditionAssessment(BaseModel):
    """Multi-condition assessment comparing all conditions against each criterion."""
    criteria_comparisons: List[CriteriaMultiConditionAssessment] = Field(
        ..., 
        description="List of multi-condition assessments for each criterion"
    )
    comparison_timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_conditions: int = Field(..., ge=2, description="Total number of conditions compared")


class ExperimentEvaluationResponse(BaseModel):
    """Response for experiment evaluation."""
    conditions: List[ConditionResult] = Field(..., description="List of evaluation results for each condition")
    multi_condition_assessment: Optional[MultiConditionAssessment] = Field(None, description="Multi-condition assessment comparing all conditions against each criterion (only present when there are 2+ conditions)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conditions": [
                    {
                        "conditionID": "run_1",
                        "persona": "Persona A",
                        "model": "gpt-4",
                        "run_index": 1,
                        "criteria": [
                            {
                                "title": "Efficiency",
                                "assertion": "steps < 10",
                                "granularity": "step_level",
                                "involved_steps": [],
                                "overall_assessment": "pass",
                                "overall_reasoning": "Completed in 5 steps",
                                "confidence": 0.95
                            }
                        ]
                    }
                ],
                "multi_condition_assessment": {
                    "total_conditions": 2,
                    "comparison_timestamp": "2023-10-27T10:00:00Z",
                    "criteria_comparisons": [
                        {
                            "title": "Efficiency",
                            "assertion": "steps < 10",
                            "granularity": "step_level",
                            "condition_comparison": {
                                "best_condition_id": "run_1",
                                "best_condition_rank": 1,
                                "ranking": [
                                    {
                                        "rank": 1,
                                        "condition_id": "run_1",
                                        "overall_assessment": "pass",
                                        "confidence": 0.95,
                                        "summary": "Fast execution",
                                        "persona": "Persona A",
                                        "model": "gpt-4",
                                        "run_index": 1
                                    }
                                ],
                                "ranking_reasoning": "Run 1 was faster.",
                                "comparison_summary": "Run 1 is more efficient."
                            }
                        }
                    ]
                }
            }
        }
    )
