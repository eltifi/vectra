"""
@file main.py
@brief FastAPI application factory and root endpoint.
@details
Initializes the Vectra FastAPI application with:
- Logging configuration
- Database initialization
- Middleware setup (CORS, Error handling)
- Router registration (API, Health)
- Documentation serving

@author Vectra Project
@date 2025-12-15
@version 1.0
@license AGPL-3.0
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi.responses import HTMLResponse

# Internal modules
from app.core.logging import setup_logging
from app.core import exceptions
from app.core import docs
from app.core.middleware import DatabaseErrorMiddleware
from app.core.cache import cache
from app.api import routes
from app.api.endpoints import health
from app.db.seed import initialize_database

# Configure logging
logger = setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    @brief Application lifecycle manager
    @details
    Handles startup and shutdown events:
    - Database initialization
    - Redis connection
    """
    # Startup
    logger.info("=" * 60)
    logger.info("Starting Vectra API...")
    logger.info("=" * 60)

    # Initialize Database
    try:
        logger.info("Initializing database...")
        if initialize_database():
             logger.info("✓ Database initialization completed")
        else:
             logger.warning("⚠ Database initialization encountered issues")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}", exc_info=True)

    # Connect Cache
    await cache.connect()
    
    yield
    
    # Shutdown
    await cache.close()
    logger.info("Vectra API shutdown completed")


## @brief FastAPI application instance
app = FastAPI(
    title="Vectra API - Vehicle Evacuation & Traffic Resilience",
    lifespan=lifespan,
    docs_url="/api/docs", # Move auto-docs to /api/docs to keep root clean
    redoc_url=None
)

# --------------------------------------------------------------------------
# Middleware
# --------------------------------------------------------------------------

# CORS
# Production Note: Restrict allow_origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Error Handling
app.add_middleware(DatabaseErrorMiddleware)


# --------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------

app.include_router(health.router)
app.include_router(routes.router) # Root level API to support frontend proxies


# --------------------------------------------------------------------------
# Exception Handlers
# --------------------------------------------------------------------------

app.add_exception_handler(HTTPException, exceptions.http_exception_handler)
app.add_exception_handler(RequestValidationError, exceptions.validation_exception_handler)
app.add_exception_handler(Exception, exceptions.general_exception_handler)


# --------------------------------------------------------------------------
# Static Files & Documentation
# --------------------------------------------------------------------------

# Mount backend technical docs (Doxygen/Sphinx generated) if they exist
backend_docs_path = Path(__file__).parent.parent / "docs" / "html"
if backend_docs_path.exists():
    app.mount("/docs/technical", StaticFiles(directory=backend_docs_path, html=True), name="technical_docs")

@app.get("/", response_class=HTMLResponse)
def read_root():
    """
    @brief Serve root documentation page
    """
    return docs.get_root_documentation()