"""
Pydantic schemas for persona generation API.
Defines request and response models for value agent persona generation.
"""
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class DemographicInfo(BaseModel):
    """
    Demographic information model for persona generation.
    
    Attributes:
        name: Person's full name (required)
        age: Person's age (required)
        job: Person's job/profession (required)
        location: Person's location (optional)
        education: Person's education background (optional)
        interests: Person's interests (optional)
    """
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Person's full name, e.g., John Smith"
    )
    age: int = Field(
        ...,
        ge=18,
        le=100,
        description="Person's age, e.g., 28"
    )
    job: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Person's job/profession, e.g., Software Engineer"
    )
    location: Optional[str] = Field(
        None,
        max_length=100,
        description="Person's location, e.g., San Francisco, CA"
    )
    education: Optional[str] = Field(
        None,
        max_length=200,
        description="Person's education background, e.g., Bachelor's in Computer Science"
    )
    interests: Optional[str] = Field(
        None,
        max_length=500,
        description="Person's interests and hobbies"
    )


class PersonaGenerationRequest(BaseModel):
    """
    Request model for persona generation endpoint.
    
    Attributes:
        demographic: Demographic information for persona generation
    """
    demographic: DemographicInfo = Field(
        ...,
        description="Demographic information to guide persona generation"
    )


class PersonaGenerationResponse(BaseModel):
    """
    Response model for persona generation endpoint.
    
    Attributes:
        persona: The generated persona description
        success: Whether the generation was successful
        error_message: Error message if generation failed
    """
    persona: Optional[str] = Field(
        None,
        description="The generated persona description"
    )
    success: bool = Field(
        default=True,
        description="Whether the generation was successful"
    )
    error_message: Optional[str] = Field(
        None,
        description="Error message if generation failed"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "persona": "John Smith is a 28-year-old Software Engineer living in San Francisco, CA. He has a Bachelor's in Computer Science and enjoys hiking and coding.",
                "success": True,
                "error_message": None
            }
        }
    )