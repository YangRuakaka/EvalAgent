"""
Dependency injection for FastAPI routes.
"""
from typing import Generator
from dataclasses import dataclass

from ..services.llm_factory import ChatLLMFactory
from ..services.task_decomposer import TaskDecomposerService
from ..services.granularity_analyzer import GranularityAnalyzerService
from ..services.step_aggregator import StepAggregatorService
from ..services.judge_evaluator import JudgeEvaluatorService


def get_db() -> Generator:
    # Example: yield SessionLocal()
    raise NotImplementedError("Configure database before using get_db")


@dataclass
class JudgeServices:
    """Container for all Judge-related services."""
    
    llm_factory: ChatLLMFactory
    task_decomposer: TaskDecomposerService
    granularity_analyzer: GranularityAnalyzerService
    step_aggregator: StepAggregatorService
    judge_evaluator: JudgeEvaluatorService


# Global service instances (lazy initialized)
_judge_services: JudgeServices | None = None


def get_judge_services() -> JudgeServices:
    """
    Get or create the JudgeServices instance.
    
    Returns:
        JudgeServices with all initialized services
    """
    
    global _judge_services
    
    if _judge_services is None:
        # Initialize all services
        llm_factory = ChatLLMFactory()
        task_decomposer = TaskDecomposerService(llm_factory)
        granularity_analyzer = GranularityAnalyzerService(llm_factory)
        step_aggregator = StepAggregatorService(llm_factory)
        judge_evaluator = JudgeEvaluatorService(
            llm_factory=llm_factory,
            decomposer=task_decomposer,
            granularity_analyzer=granularity_analyzer,
            step_aggregator=step_aggregator
        )
        
        _judge_services = JudgeServices(
            llm_factory=llm_factory,
            task_decomposer=task_decomposer,
            granularity_analyzer=granularity_analyzer,
            step_aggregator=step_aggregator,
            judge_evaluator=judge_evaluator
        )
    
    return _judge_services
