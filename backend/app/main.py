
import asyncio
import logging
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import api_router
from .api.history_logs import preload_history_logs_cache
from .core.config import settings
import uvicorn


if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="Backend API with FastAPI"
)
logger = logging.getLogger(__name__)

# @app.middleware("http")
# async def log_requests(request: Request, call_next):
#     # Log Request
#     body_bytes = await request.body()
    
#     # Restore body for the handler
#     async def receive():
#         return {"type": "http.request", "body": body_bytes}
#     request._receive = receive
    
#     print(f"\n>>> [REQUEST] {request.method} {request.url}")
#     if body_bytes:
#         try:
#             print(f">>> [REQUEST BODY] {body_bytes.decode('utf-8')[:2000]}")
#         except:
#              print(f">>> [REQUEST BODY] (binary data) {len(body_bytes)} bytes")

#     response = await call_next(request)
    
#     # Log Response
#     # Only capture body for non-streaming, text-based responses to avoid issues
#     content_type = response.headers.get("content-type", "")
#     if "text" in content_type or "json" in content_type:
#         response_body = b""
#         async for chunk in response.body_iterator:
#             response_body += chunk
            
#         print(f"<<< [RESPONSE] Status: {response.status_code}")
#         try:
#             # Try to decode as utf-8, fallback to string representation
#             print(f"<<< [RESPONSE BODY] {response_body.decode('utf-8')[:2000]}")
#         except:
#             print(f"<<< [RESPONSE BODY] (decoding error) {len(response_body)} bytes")
            
#         # Reconstruct response to pass it downstream
#         new_response = Response(
#             content=response_body,
#             status_code=response.status_code,
#             headers=dict(response.headers),
#             media_type=response.media_type
#         )
#         new_response.background = response.background
#         return new_response
#     else:
#         print(f"<<< [RESPONSE] Status: {response.status_code} (Body not logged for {content_type})")
#         return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_origin_regex=f"({settings.CORS_ALLOW_ORIGIN_REGEX})|({settings.CORS_ALLOW_LOCALHOST_REGEX})",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
async def preload_history_logs_on_startup() -> None:
    if not settings.HISTORY_LOGS_PRELOAD_ENABLED:
        logger.info("history logs preload disabled")
        return

    preload_result = await asyncio.to_thread(preload_history_logs_cache)
    logger.info(
        "history logs preload completed: mode=%s datasets=%s warmed=%s errors=%s",
        preload_result.get("mode"),
        preload_result.get("datasets"),
        preload_result.get("warmed_counts"),
        preload_result.get("errors"),
    )


if __name__ == "__main__":
    print("running main")
    uvicorn.run(
        "app.main:app",
        port=settings.API_PORT,
        host=settings.API_HOST,
        log_level="info",
        reload=settings.API_RELOAD,
        workers=settings.API_WORKERS,
    )