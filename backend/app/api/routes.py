from fastapi import APIRouter
from . import browser_agent, configuration, health, history_logs, sample, criteria, judge
from ..core.config import settings

api_router = APIRouter(prefix=settings.API_V1_PREFIX)
api_router.include_router(configuration.router)
api_router.include_router(health.router)
api_router.include_router(sample.router)
api_router.include_router(browser_agent.router)
api_router.include_router(history_logs.router)
api_router.include_router(criteria.router)
api_router.include_router(judge.router)

