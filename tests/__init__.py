"""
Test Suite for Vectra Backend

This package contains comprehensive unit tests, integration tests, and fixtures
for the Vectra geospatial emergency evacuation analysis platform.

Test Categories:
- test_etl: Tests for FDOT data ETL pipeline
- test_models: Tests for SQLAlchemy ORM models
- test_api: Tests for FastAPI endpoints
- test_services: Tests for evacuation simulation service
- conftest.py: Shared fixtures and test configuration

Running Tests:
    pytest              # Run all tests
    pytest -v           # Verbose output
    pytest tests/test_etl.py -v  # Run specific test file
    pytest --cov        # With coverage report

Author: Vectra Project
License: AGPL-3.0
"""
