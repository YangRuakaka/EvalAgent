
import asyncio
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import api_router
from .core.config import settings
import uvicorn


if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="Backend API with FastAPI"
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Log Request
    body_bytes = await request.body()
    
    # Restore body for the handler
    async def receive():
        return {"type": "http.request", "body": body_bytes}
    request._receive = receive
    
    print(f"\n>>> [REQUEST] {request.method} {request.url}")
    if body_bytes:
        try:
            print(f">>> [REQUEST BODY] {body_bytes.decode('utf-8')[:2000]}")
        except:
             print(f">>> [REQUEST BODY] (binary data) {len(body_bytes)} bytes")

    response = await call_next(request)
    
    # Log Response
    # Only capture body for non-streaming, text-based responses to avoid issues
    content_type = response.headers.get("content-type", "")
    if "text" in content_type or "json" in content_type:
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk
            
        print(f"<<< [RESPONSE] Status: {response.status_code}")
        try:
            # Try to decode as utf-8, fallback to string representation
            print(f"<<< [RESPONSE BODY] {response_body.decode('utf-8')[:2000]}")
        except:
            print(f"<<< [RESPONSE BODY] (decoding error) {len(response_body)} bytes")
            
        # Reconstruct response to pass it downstream
        new_response = Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )
        new_response.background = response.background
        return new_response
    else:
        print(f"<<< [RESPONSE] Status: {response.status_code} (Body not logged for {content_type})")
        return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


if __name__ == "__main__":
	print("running main")
	uvicorn.run("app.main:app", port=8000, host="0.0.0.0", log_level="info", reload=True, workers=1)