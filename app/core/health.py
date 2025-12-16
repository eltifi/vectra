"""
@file health.py
@brief System health checks and status monitoring

@details
Provides health check endpoints and status monitoring for:
- PostgreSQL database connectivity
- Redis cache connectivity
- Application readiness

Returns appropriate HTTP status codes and messages for system maintenance scenarios.

@author Vectra Project
@date 2025-12-13
@version 1.0
@license AGPL-3.0
"""

import logging
from typing import Dict, Any
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.db.database import SessionLocal
from app.core.cache import cache

logger = logging.getLogger(__name__)


class HealthStatus:
    """Health status indicator for system components"""
    
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


async def check_database() -> Dict[str, Any]:
    """
    @brief Check PostgreSQL database connectivity
    
    @return Dict with status, message, and response time
    @details
    Attempts a simple query to verify database connectivity.
    Returns degraded status if query fails.
    """
    try:
        db = SessionLocal()
        result = db.execute(text("SELECT 1"))
        db.close()
        return {
            "status": HealthStatus.HEALTHY,
            "message": "PostgreSQL database is healthy",
            "component": "database"
        }
    except OperationalError as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": "PostgreSQL database is unavailable",
            "component": "database",
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Unexpected database health check error: {e}")
        return {
            "status": HealthStatus.DEGRADED,
            "message": "Database health check encountered an error",
            "component": "database",
            "error": str(e)
        }


async def check_cache() -> Dict[str, Any]:
    """
    @brief Check Redis cache connectivity
    
    @return Dict with status, message
    @details
    Attempts a PING to Redis to verify connectivity.
    Redis is optional - degraded status if unavailable.
    """
    try:
        if not cache.client:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": "Redis cache is not initialized",
                "component": "cache"
            }
        
        await cache.client.ping()
        return {
            "status": HealthStatus.HEALTHY,
            "message": "Redis cache is healthy",
            "component": "cache"
        }
    except Exception as e:
        logger.warning(f"Cache health check failed: {e}")
        return {
            "status": HealthStatus.DEGRADED,
            "message": "Redis cache is unavailable (running in degraded mode)",
            "component": "cache",
            "error": str(e)
        }


async def get_system_health() -> Dict[str, Any]:
    """
    @brief Get comprehensive system health status
    
    @return Dict with overall status and component details
    @details
    Checks all critical components and determines overall system status.
    - HEALTHY: All components operational
    - DEGRADED: Database OK, cache issues or non-critical components down
    - UNHEALTHY: Database unavailable (critical failure)
    """
    db_status = await check_database()
    cache_status = await check_cache()
    
    # Determine overall health
    if db_status["status"] == HealthStatus.UNHEALTHY:
        overall_status = HealthStatus.UNHEALTHY
    elif db_status["status"] == HealthStatus.DEGRADED or \
         cache_status["status"] == HealthStatus.DEGRADED:
        overall_status = HealthStatus.DEGRADED
    else:
        overall_status = HealthStatus.HEALTHY
    
    return {
        "status": overall_status,
        "components": {
            "database": db_status,
            "cache": cache_status
        },
        "message": get_status_message(overall_status)
    }


def get_status_message(status: str) -> str:
    """Get human-readable status message"""
    messages = {
        HealthStatus.HEALTHY: "System is operational",
        HealthStatus.DEGRADED: "System is running with reduced functionality (non-critical services unavailable)",
        HealthStatus.UNHEALTHY: "System is in maintenance mode (critical services unavailable)"
    }
    return messages.get(status, "Unknown status")
