"""
API endpoints for criteria generation.
Provides REST API for generating evaluation criteria using LLM.
"""
import logging
from fastapi import APIRouter, HTTPException
from typing import List

from ..schemas.criteria import CriteriasGenerationRequest, CriteriasGenerationResponse
from ..services.criteria_generator import CriteriaGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/criteria", tags=["criteria"])


@router.post(
    "/generate",
    response_model=CriteriasGenerationResponse,
    summary="Generate evaluation criteria",
    description="Generate evaluation criteria for a task based on personas and models"
)
async def generate_criteria(
    request: CriteriasGenerationRequest
) -> CriteriasGenerationResponse:
    """
    Generate evaluation criteria for a given task.
    
    Args:
        request: CriteriasGenerationRequest containing task details, personas, and models
        
    Returns:
        CriteriasGenerationResponse with generated criteria
        
    Raises:
        HTTPException: If criteria generation fails
    """
    try:
        logger.info(f"Generating criteria for task: {request.task_name}")
        
        # Create generator with default model and provider
        generator = CriteriaGenerator(
            model_name="deepseek-chat",
            provider="deepseek"
        )
        
        # Generate criteria
        response = await generator.generate_criteria(
            task_name=request.task_name,
            task_url=request.task_url,
            personas=request.personas,
            models=request.models
        )
        
        logger.info(f"Successfully generated criteria for task: {request.task_name}")
        return response
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating criteria: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate criteria: {str(e)}"
        )


@router.get(
    "/health",
    summary="Check criteria generation service health"
)
async def criteria_health():
    """
    Health check endpoint for criteria generation service.
    
    Returns:
        Health status
    """
    return {"status": "ok", "service": "criteria_generation"}
