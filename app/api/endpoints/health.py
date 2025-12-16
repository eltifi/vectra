"""
@file health.py
@brief Health check API endpoints
@details
Provides endpoints for monitoring system status, readiness, and liveness.
Includes maintenance mode support when critical services are down.

@author Vectra Project
@date 2025-12-15
@version 1.0
@license AGPL-3.0
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.core.health import get_system_health, HealthStatus

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    """
    @brief Get system health status
    
    @details
    Provides comprehensive health information about critical systems:
    - Database connectivity
    - Cache status
    
    Returns 503 if system is in maintenance mode or degraded.
    """
    health = await get_system_health()
    
    if health["status"] == HealthStatus.UNHEALTHY:
        return JSONResponse(
            status_code=503,
            content={
                "status": health["status"],
                "message": health["message"],
                "components": health["components"],
                "note": "System is in maintenance mode. Critical services are unavailable."
            }
        )
    elif health["status"] == HealthStatus.DEGRADED:
        return JSONResponse(
            status_code=503,
            content={
                "status": health["status"],
                "message": health["message"],
                "components": health["components"],
                "note": "System is running with reduced functionality."
            }
        )
    
    return {
        "status": health["status"],
        "message": health["message"],
        "components": health["components"]
    }

@router.get("/health/ready")
async def readiness_check():
    """
    @brief Kubernetes readiness probe
    @details Returns 200 only if system is fully operational.
    """
    health = await get_system_health()
    
    if health["status"] == HealthStatus.HEALTHY:
        return {"ready": True, "status": "System is ready"}
    else:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "status": "System is not ready",
                "reason": health["message"]
            }
        )

@router.get("/health/live")
async def liveness_check():
    """
    @brief Kubernetes liveness probe
    @details Returns 200 as long as application is running.
    """
    return {"alive": True, "status": "Application is running"}
