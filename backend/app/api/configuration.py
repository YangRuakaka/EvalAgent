"""Unified configuration API module combining persona and persona variation management."""
from typing import Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..schemas.persona import (
    PersonaGenerationRequest,
    PersonaGenerationResponse,
)
from ..services.persona_generator import (
    create_persona_generator_service,
    PersonaGeneratorService,
)
from ..schemas.persona_variation import (
    PersonaVariation,
    PersonaVariationRequest,
    PersonaVariationResponse,
)
from ..services.persona_variation_generator import (
    create_persona_variation_generator_service,
    PersonaVariationGeneratorService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["configuration"])

def get_persona_generator_service() -> PersonaGeneratorService:
    """Dependency to get persona generator service instance."""

    return create_persona_generator_service()


@router.post(
    "/persona/generate",
    response_model=PersonaGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Value Agent Persona",
    description="Generate a detailed persona based on demographic information for value-based product evaluation",
)
async def generate_persona(
    request: PersonaGenerationRequest,
    service: PersonaGeneratorService = Depends(get_persona_generator_service),
) -> PersonaGenerationResponse:
    """Generate a value agent persona based on provided demographic information."""

    try:
        logger.info("Received persona generation request with demographic: %s", request.demographic)

        if (
            not request.demographic.name
            or not request.demographic.age
            or not request.demographic.job
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name, age, and job are required fields in demographic information",
            )

        demographic_dict = {
            "name": request.demographic.name,
            "age": request.demographic.age,
            "job": request.demographic.job,
            "location": request.demographic.location,
            "education": request.demographic.education,
            "interests": request.demographic.interests,
        }

        result = await service.generate_persona(demographic=demographic_dict)

        if result["success"]:
            logger.info("Persona generation completed successfully")
            return PersonaGenerationResponse(
                persona=result["persona"],
                success=True,
                error_message=None,
            )

        logger.error("Persona generation failed: %s", result["error_message"])
        return PersonaGenerationResponse(
            persona=None,
            success=False,
            error_message=result["error_message"],
        )

    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unexpected error in persona generation: %s", exc)
        return PersonaGenerationResponse(
            persona=None,
            success=False,
            error_message="An unexpected error occurred during persona generation",
        )


def get_persona_variation_generator_service() -> PersonaVariationGeneratorService:
    """Dependency to get persona variation generator service instance."""

    return create_persona_variation_generator_service()


@router.post(
    "/persona-variation/generate",
    response_model=PersonaVariationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Persona Variations Based on Values",
    description="Generate multiple persona variations from a base persona, with each variation emphasizing a different value using few-shot prompting",
)
async def generate_persona_variations(
    request: PersonaVariationRequest,
    service: PersonaVariationGeneratorService = Depends(get_persona_variation_generator_service),
) -> PersonaVariationResponse:
    """Generate persona variations based on different values using few-shot prompting."""

    try:
        logger.info("Persona variation request received for %d values", len(request.values))

        if not request.persona.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Base persona cannot be empty or contain only whitespace",
            )

        if not request.values:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one value must be provided for variation generation",
            )

        for index, value in enumerate(request.values):
            if not value.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Value at index {index} cannot be empty or contain only whitespace",
                )

        result = await service.generate_persona_variations(
            persona=request.persona,
            values=request.values,
        )

        if result["success"]:
            logger.info(
                "Persona variation generation completed: %d variations",
                len(result["variations"]),
            )

            successful_variations = [
                variation
                for variation in result["variations"]
                if variation.get("varied_persona") is not None
            ]

            if not successful_variations:
                return PersonaVariationResponse(
                    variations=None,
                    success=False,
                    error_message="All variation generations failed. Please check the logs for details.",
                )

            return PersonaVariationResponse(
                variations=successful_variations,
                success=True,
                error_message=None,
            )

        logger.error("Persona variation generation failed: %s", result["error_message"])
        return PersonaVariationResponse(
            variations=None,
            success=False,
            error_message=result["error_message"],
        )

    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unexpected error in persona variation generation: %s", exc)
        return PersonaVariationResponse(
            variations=None,
            success=False,
            error_message="An unexpected error occurred during persona variation generation",
        )

