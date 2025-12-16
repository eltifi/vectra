"""
@file middleware.py
@brief Custom middleware for error handling and request processing

@details
Provides centralized middleware for:
- Catching unhandled database errors
- Providing consistent error responses
- Request logging and monitoring

@author Vectra Project
@date 2025-12-13
@version 1.0
@license AGPL-3.0
"""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.exc import DatabaseError, OperationalError

logger = logging.getLogger(__name__)


class DatabaseErrorMiddleware(BaseHTTPMiddleware):
    """
    @brief Middleware to catch database errors and return proper status messages
    
    @details
    Intercepts unhandled database exceptions and returns appropriate HTTP responses.
    Allows health check endpoints to work even when database is unavailable.
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        @brief Process request and catch database errors
        
        @param request The HTTP request
        @param call_next The next middleware/route handler
        @return Response or error response
        """
        try:
            response = await call_next(request)
            return response
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Database error handling {request.method} {request.url.path}: {e}")
            
            # Health check endpoints should manage their own errors, but if one bubbles up,
            # we just return the maintenance response.

            
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Service unavailable",
                    "message": "Database connection failed. System is in maintenance mode.",
                    "status": "unavailable"
                }
            )
        except Exception as e:
            logger.exception(f"Unexpected error handling {request.method} {request.url.path}: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "message": "An unexpected error occurred. Please try again later.",
                    "status": "error"
                }
            )
