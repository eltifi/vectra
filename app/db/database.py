"""
@file database.py
@brief SQLAlchemy database engine and session configuration

@details
This module provides centralized database connection management for Vectra.
Configures PostgreSQL/PostGIS engine, session factory, and dependency injection
for FastAPI routes.

@author Vectra Project
@date 2025-12-12
@version 1.0
@license AGPL-3.0

@see models.road_network for ORM models
@see db.seed for database initialization
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os

## @brief PostgreSQL connection URL from environment or default
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:mysecretpassword@localhost:5432/vectra"
)

## @brief SQLAlchemy engine instance
## Handles connection pooling and PostgreSQL/PostGIS queries
engine = create_engine(DATABASE_URL)

## @brief Session factory for creating database sessions
## Configured with autocommit=False and autoflush=False for explicit transaction control
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

## @brief SQLAlchemy declarative base (legacy import, use db.base.Base)
Base = declarative_base()


def get_db():
    """
    @brief FastAPI dependency for database session injection
    
    @details
    Provides a database session for a single request lifecycle.
    Used as a dependency in FastAPI route handlers to enable ORM queries.
    Automatically closes the session after request completion.
    
    Returns 503 Service Unavailable if database connection fails.
    
    @return Generator yielding a SQLAlchemy Session instance
    
    @throws HTTPException with status_code=503 if database connection fails
    
    @note
    Used with FastAPI Depends() parameter:
    
    @code{.python}
    @router.get("/segments")
    def get_segments(db: Session = Depends(get_db)):
        segments = db.query(RoadSegment).all()
        return segments
    @endcode
    
    @see api.routes for usage examples
    """
    from fastapi import HTTPException
    from sqlalchemy.exc import OperationalError
    
    db = SessionLocal()
    try:
        # Test connection
        db.execute(text("SELECT 1"))
        yield db
    except OperationalError as e:
        db.close()
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable. System is in maintenance mode."
        )
    except Exception as e:
        db.close()
        raise HTTPException(
            status_code=503,
            detail="Database error. Please try again later."
        )
    finally:
        db.close()
