"""
@file __init__.py
@brief Vectra backend application package initialization

@details
Package defining the main FastAPI application and supporting modules for
geospatial emergency evacuation network analysis.

**Package Structure:**
- api/: FastAPI route handlers and endpoint definitions
- models/: SQLAlchemy ORM models for database schema
- services/: Business logic layer (evacuation simulation, algorithms)
- db/: Database configuration, session management, and initialization
- etl/: Extract-Transform-Load pipeline for FDOT data ingestion
- config/: Application configuration files (scenarios, parameters)

@author Vectra Project
@date 2025-12-12
@version 1.0
@license AGPL-3.0

@see main for FastAPI application setup
@see api.routes for endpoint documentation
@see models.road_network for data model definitions
"""
