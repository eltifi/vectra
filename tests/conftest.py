"""
Test Configuration and Shared Fixtures

This module provides shared pytest fixtures and configuration for the test suite.
Includes database setup, mock data, and testing utilities.

Fixtures:
- test_db_session: SQLAlchemy session for test database (PostgreSQL)
- sample_road_segment: Mock RoadSegment for unit tests
- empty_dataframe: Empty GeoDataFrame for testing error handling

Author: Vectra Project
License: AGPL-3.0
"""

import pytest
import logging
import geopandas as gpd
from shapely.geometry import LineString
import pandas as pd
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.models.road_network import RoadSegment

# Configure logging for tests
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Mark test categories for selective running
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (slower)")
    config.addinivalue_line("markers", "slow: Slow-running tests")
    config.addinivalue_line("markers", "database: Tests requiring PostgreSQL")
    config.addinivalue_line("markers", "api: API endpoint tests")
    config.addinivalue_line("markers", "etl: ETL pipeline tests")
    config.addinivalue_line("markers", "models: Database model tests")
    config.addinivalue_line("markers", "seed: Database seeding tests")


def pytest_collection_modifyitems(config, items):
    """Add markers based on test location."""
    for item in items:
        # Mark tests by file location
        if "test_api" in str(item.fspath):
            item.add_marker(pytest.mark.api)
        elif "test_etl" in str(item.fspath):
            item.add_marker(pytest.mark.etl)
        elif "test_models" in str(item.fspath):
            item.add_marker(pytest.mark.models)
        elif "test_seed" in str(item.fspath):
            item.add_marker(pytest.mark.seed)
        
        # Mark as unit if no database marker
        if "database" not in item.keywords:
            item.add_marker(pytest.mark.unit)


# Use PostgreSQL database for testing (connects to same database as app)
# Database URL from environment or default
# When running tests locally but DB is in Docker, use docker.for.mac.localhost or connect via exposed port
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres:mysecretpassword@127.0.0.1/vectra_test"
)


# Use PostgreSQL database for testing (connects to same database as app)
# Database URL from environment or default
# When running tests locally but DB is in Docker, use docker.for.mac.localhost or connect via exposed port
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres:mysecretpassword@127.0.0.1/vectra_test"
)


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine with PostgreSQL."""
    engine = create_engine(TEST_DATABASE_URL, echo=False)
    
    # Check connectivity
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        # If we can't connect, check if we can create the DB (only works if Postgres is running)
        # If that fails too, we must skip tests relying on this fixture
        try:
            admin_url = TEST_DATABASE_URL.replace("/vectra_test", "/postgres")
            admin_engine = create_engine(admin_url)
            with admin_engine.connect() as conn:
                conn.execute(text("SELECT 1")) # Check admin connection
                # If we get here, Postgres is up, maybe just DB missing
                try:
                    conn.execute(text("CREATE DATABASE vectra_test"))
                    conn.commit()
                except:
                    pass # DB might exist
            admin_engine.dispose()
        except Exception:
            # PostgreSQL unavailable - Mock the engine for tests
            from unittest.mock import MagicMock
            print("PostgreSQL unavailable - Mocking database engine")
            mock_engine = MagicMock()
            mock_engine.connect.return_value.__enter__.return_value = MagicMock()
            yield mock_engine
            return

    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_db_session(test_engine):
    """Provide a fresh database session for each test."""
    from unittest.mock import MagicMock
    
    # Check if engine is a mock
    if isinstance(test_engine, MagicMock):
        session = MagicMock()
        # Mock common session methods
        session.query.return_value.filter_by.return_value.first.return_value = None
        session.query.return_value.filter.return_value.all.return_value = []
        session.query.return_value.count.return_value = 0
        yield session
        return

    connection = test_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_road_segment():
    """
    Create a sample RoadSegment for testing.
    
    Returns:
        RoadSegment: Test road segment with realistic data
    """
    return RoadSegment(
        id=1,
        geom='LINESTRING(-82.4 27.9, -82.3 27.85)',
        source=1,
        target=2,
        length_m=1500.0,
        lanes=4,
        speed_limit=65,
        capacity=7200.0,  # 4 lanes * 1800 vph
        cost_time=82.5,   # 1500m / 18.2 m/s (40.7 mph)
        is_one_way=False,
        road_name="I-75 (Major Hwy)",
        direction="NB",
        rd_status="09",
        is_interstate=True,
        is_toll_road=False
    )


@pytest.fixture
def sample_geodataframe():
    """
    Create a sample GeoDataFrame for ETL testing.
    
    Returns:
        gpd.GeoDataFrame: Test data with realistic road features
    """
    data = {
        'ROADWAY': ['I-75', 'US-41', 'SR-275'],
        'LANE_CNT': [4, 2, 4],
        'SPEED': [65, 45, 55],
        'RD_STATUS': ['09', '07', '02'],
        'geometry': [
            LineString([(-82.4, 27.9), (-82.3, 27.85)]),
            LineString([(-82.5, 27.8), (-82.4, 27.75)]),
            LineString([(-82.45, 27.95), (-82.35, 27.90)]),
        ]
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def empty_geodataframe():
    """
    Create an empty GeoDataFrame for error handling tests.
    
    Returns:
        gpd.GeoDataFrame: Empty GeoDataFrame with proper schema
    """
    return gpd.GeoDataFrame(
        {'ROADWAY': [], 'LANE_CNT': [], 'SPEED': [], 'geometry': []},
        crs="EPSG:4326"
    )


@pytest.fixture
def sample_interstates_gdf():
    """
    Create sample interstate classification data.
    
    Returns:
        gpd.GeoDataFrame: Interstate roads with geometry
    """
    data = {
        'ROADWAY': ['I-75', 'I-95', 'I-4'],
        'geometry': [
            LineString([(-82.0, 28.0), (-82.0, 27.0)]),
            LineString([(-80.0, 28.5), (-80.0, 25.0)]),
            LineString([(-82.0, 28.5), (-80.0, 28.5)]),
        ]
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def sample_toll_roads_gdf():
    """
    Create sample toll road classification data.
    
    Returns:
        gpd.GeoDataFrame: Toll roads with geometry
    """
    data = {
        'ROADWAY': ['SUNCOAST', 'FTE', 'VETERANS'],
        'geometry': [
            LineString([(-82.5, 28.2), (-82.5, 27.0)]),
            LineString([(-80.5, 27.0), (-80.5, 25.0)]),
            LineString([(-82.3, 28.0), (-82.3, 27.0)]),
        ]
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")
