"""
@file exceptions.py
@brief Centralized exception handlers
@details
Provides consistent JSON error responses for HTTP exceptions, 
validation errors, and unexpected server errors.

@author Vectra Project
@date 2025-12-15
@version 1.0
@license AGPL-3.0
"""

import logging
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi import Request

logger = logging.getLogger(__name__)

async def http_exception_handler(request: Request, exc: HTTPException):
    """
    @brief Custom HTTP exception handler
    @details Provides consistent error responses across the API.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": str(exc.detail),
            "status_code": exc.status_code,
            "message": f"Request failed with HTTP {exc.status_code}"
        }
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    @brief Custom validation error handler
    @details Provides user-friendly validation error messages.
    """
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "details": exc.errors(),
            "message": "Request validation failed. Check parameters and try again."
        }
    )

async def general_exception_handler(request: Request, exc: Exception):
    """
    @brief Catch-all exception handler
    @details
    Handles unexpected exceptions gracefully.
    Logs full error for debugging while returning safe message to client.
    """
    logger.exception(f"Unexpected error handling {request.url}: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later.",
            "status": "error"
        }
    )
