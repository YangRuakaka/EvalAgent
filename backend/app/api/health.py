from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str


@router.get("/health", response_model=HealthResponse, tags=["health"], summary="Health check")
async def health_check() -> HealthResponse:
    """
    Health check endpoint to verify the API is running.
    
    Returns:
        HealthResponse: Status information
    """
    return HealthResponse(status="ok")