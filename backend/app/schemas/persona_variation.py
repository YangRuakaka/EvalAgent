"""Schemas for persona variation generation."""

from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class PersonaVariation(BaseModel):
    """A single persona variation emphasizing a specific value."""

    value: str = Field(
        ...,
        description="The value emphasized in this variation",
    )
    varied_persona: str = Field(
        ...,
        description="The persona description rewritten to highlight this value",
    )


class PersonaVariationRequest(BaseModel):
    """Request body for persona variation generation."""

    persona: str = Field(
        ...,
        min_length=10,
        description="The base persona description that will be varied",
    )
    values: List[str] = Field(
        ...,
        min_items=1,
        description="List of values to generate persona variations for",
    )


class PersonaVariationResponse(BaseModel):
    """Response payload for persona variation generation."""

    variations: Optional[List[PersonaVariation]] = Field(
        None,
        description="Generated persona variations for each requested value",
    )
    success: bool = Field(
        default=True,
        description="Whether the generation completed successfully",
    )
    error_message: Optional[str] = Field(
        None,
        description="Error details when generation fails",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "variations": [
                    {
                        "value": "Frugality",
                        "varied_persona": "John is very careful with his spending..."
                    },
                    {
                        "value": "Efficiency",
                        "varied_persona": "John optimizes every action to save time..."
                    }
                ],
                "success": True,
                "error_message": None
            }
        }
    )


__all__ = [
    "PersonaVariation",
    "PersonaVariationRequest",
    "PersonaVariationResponse",
]
