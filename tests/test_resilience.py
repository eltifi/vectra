
import pytest
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.core.middleware import DatabaseErrorMiddleware
from app.api import routes

# Setup mock app
app = FastAPI()
app.add_middleware(DatabaseErrorMiddleware)

@app.get("/test-db-error")
def trigger_db_error():
    raise OperationalError("SELECT 1", {}, "Mock DB Error")

@app.get("/test-generic-error")
def trigger_generic_error():
    raise Exception("Boom")

client = TestClient(app)

def test_database_error_middleware():
    """Test that middleware catches DB errors and returns 503"""
    response = client.get("/test-db-error")
    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "Service unavailable"
    assert "Database connection failed" in data["message"]

def test_generic_error_middleware():
    """Test that middleware catches generic errors and returns 500"""
    response = client.get("/test-generic-error")
    assert response.status_code == 500
    data = response.json()
    assert data["error"] == "Internal server error"

@patch("app.core.health.check_database")
@patch("app.core.health.check_cache")
def test_health_check_unhealthy(mock_cache, mock_db):
    """Test health check when DB is down"""
    from app.core.health import HealthStatus, get_system_health
    import asyncio
    
    # Mock return values for async functions
    mock_db.return_value = {"status": HealthStatus.UNHEALTHY, "component": "database"}
    mock_cache.return_value = {"status": HealthStatus.HEALTHY, "component": "cache"}
    
    # We need to run the async function
    loop = asyncio.new_event_loop()
    health = loop.run_until_complete(get_system_health())
    loop.close()
    
    assert health["status"] == HealthStatus.UNHEALTHY
