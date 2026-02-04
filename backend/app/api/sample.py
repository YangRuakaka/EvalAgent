from fastapi import APIRouter
from ..schemas.echo import EchoRequest, EchoResponse
from datetime import datetime, timezone

router = APIRouter()

@router.post("/echo", response_model=EchoResponse, summary="Echo example")
async def echo(payload: EchoRequest) -> EchoResponse:
    return EchoResponse(message=payload.message, server_time=datetime.now(timezone.utc))
