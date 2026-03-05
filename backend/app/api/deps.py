"""
Dependency injection for FastAPI routes.
"""
from typing import Generator
from dataclasses import dataclass

from ..services.llm_factory import ChatLLMFactory
from ..services.judge_evaluator import JudgeEvaluatorService


def get_db() -> Generator:
    # Example: yield SessionLocal()
    raise NotImplementedError("Configure database before using get_db")


@dataclass
class JudgeServices:
    """Container for all Judge-related services."""
    
    llm_factory: ChatLLMFactory
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
        judge_evaluator = JudgeEvaluatorService(llm_factory=llm_factory)
        
        _judge_services = JudgeServices(
            llm_factory=llm_factory,
            judge_evaluator=judge_evaluator
        )
    
    return _judge_services
