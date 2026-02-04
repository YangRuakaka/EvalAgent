"""
Pydantic schemas for criteria generation API.
Defines request and response models for evaluation criteria generation.
"""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field


class CriteriasGenerationRequest(BaseModel):
    """
    Request model for criteria generation.
    
    Attributes:
        task_name: Name of the task to evaluate
        task_url: URL of the task
        personas: List of personas to consider
        models: List of models to evaluate
    """
    task_name: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Task name, e.g., 'Buy milk from supermarket'"
    )
    task_url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Task URL where the agent will perform the task"
    )
    personas: List[str] = Field(
        ...,
        min_items=1,
        description="List of personas to consider for evaluation"
    )
    models: List[str] = Field(
        ...,
        min_items=1,
        description="List of models to evaluate"
    )


class Criteria(BaseModel):
    """
    Individual evaluation criteria.
    
    Attributes:
        name: Criteria name
        description: Detailed description of the criteria
        assertion: Assertion or method to verify this criteria
    """
    name: str = Field(
        ...,
        description="Criteria name, e.g., 'Task Completion'"
    )
    description: str = Field(
        ...,
        description="Detailed description of what this criteria evaluates"
    )
    assertion: str = Field(
        ...,
        description="How to verify/assert this criteria"
    )


class CriteriasGenerationResponse(BaseModel):
    """
    Response model for criteria generation.
    
    Attributes:
        task_name: Task name
        criteria_list: List of generated evaluation criteria
    """
    task_name: str = Field(
        ...,
        description="Task name"
    )
    criteria_list: List[Criteria] = Field(
        ...,
        description="List of generated evaluation criteria"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_name": "Buy milk from supermarket",
                "criteria_list": [
                    {
                        "name": "Task Completion",
                        "description": "The agent successfully bought milk.",
                        "assertion": "The final page shows a receipt for milk."
                    },
                    {
                        "name": "Efficiency",
                        "description": "The agent completed the task in fewer than 10 steps.",
                        "assertion": "step_count < 10"
                    }
                ]
            }
        }
    }
