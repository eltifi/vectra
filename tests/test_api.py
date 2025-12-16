"""
API Endpoint Tests

Tests for all FastAPI endpoints in the Vectra backend.
Covers request/response handling, error cases, and data validation.

Test Classes:
- TestRootEndpoint: GET / documentation endpoint
- TestSegmentsEndpoint: GET /api/segments road network data
- TestSimulateEndpoint: GET /api/simulate evacuation simulation
- TestHurricaneScenarios: GET /api/hurricane-scenarios scenario data

Author: Vectra Project
License: AGPL-3.0
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
import json



# Mock dependencies
from app.db.database import get_db
from app.core.cache import cache
from unittest.mock import AsyncMock, MagicMock, patch

# Mock DB Session
mock_session = MagicMock()
mock_session.execute.return_value.scalar.return_value = {
    "type": "FeatureCollection", 
    "features": [{
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": []},
        "properties": {"id": 1, "name": "I-75", "road_type": "interstate", "lanes": 4, "speed_limit": 70}
    }]
} 

# Mock Cache
async def mock_get_cache(*args):
    return None
async def mock_set_cache(*args, **kwargs):
    return None

app.dependency_overrides[get_db] = lambda: mock_session
cache.get = AsyncMock(side_effect=mock_get_cache)
cache.set = AsyncMock(side_effect=mock_set_cache)

client = TestClient(app)


class TestRootEndpoint:
    """Test GET / documentation endpoint."""
    
    def test_root_returns_html(self):
        """Test that root endpoint returns HTML documentation."""
        response = client.get("/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Vectra API" in response.text
        assert "Vehicle Evacuation" in response.text
    
    def test_root_includes_legal_notice(self):
        """Test that root endpoint includes FDOT disclaimer."""
        response = client.get("/")
        
        assert response.status_code == 200
        assert "FDOT" in response.text
        assert "not affiliated" in response.text
    
    def test_root_documents_endpoints(self):
        """Test that root documents available endpoints."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Vectra API" in response.text
        assert "/segments" in response.text
        assert "/simulate" in response.text
        assert "/scenarios" in response.text
    
    def test_root_accessible_without_auth(self):
        """Test that root endpoint requires no authentication."""
        response = client.get("/")
        
        # Should not redirect or require auth
        assert response.status_code == 200
        assert response.status_code != 401
        assert response.status_code != 403


class TestSegmentsEndpoint:
    """Test GET /api/segments road network endpoint."""
    
    def test_segments_returns_json(self):
        """Test that endpoint returns valid JSON GeoJSON."""
        response = client.get("/segments")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        # Verify JSON structure
        data = response.json()
        assert "type" in data
        assert "features" in data
    
    def test_get_segments_success(self, test_db_session, sample_road_segment):
        """Test retrieving segments."""
        test_db_session.add(sample_road_segment)
        test_db_session.commit()
        
        # Mock EvacuationService or ensure data is ready
        # In this unit test, we just check endpoint response with seeded data
        
        response = client.get("/segments")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 1
        
        # Each feature should be valid
        if len(data["features"]) > 0:
            feature = data["features"][0]
            assert feature["type"] == "Feature"
            assert "geometry" in feature
            assert "properties" in feature
    
    def test_segments_geojson_structure(self):
        """Test that response conforms to GeoJSON spec."""
        response = client.get("/segments")
        data = response.json()
        
        # Valid GeoJSON FeatureCollection
        assert data["type"] == "FeatureCollection"
        assert isinstance(data["features"], list)
        
        # Each feature should be valid
        if len(data["features"]) > 0:
            feature = data["features"][0]
            assert feature["type"] == "Feature"
            assert "geometry" in feature
            assert "properties" in feature
    
    def test_segments_contains_required_properties(self):
        """Test that road segments include required properties."""
        response = client.get("/segments")
        data = response.json()
        
        if len(data["features"]) > 0:
            props = data["features"][0]["properties"]
            
            # Required properties
            assert "id" in props
            assert "name" in props
            assert "road_type" in props
    
    def test_segments_road_types_valid(self):
        """Test that road_type values are from valid set."""
        response = client.get("/segments")
        data = response.json()
        
        valid_types = {"interstate", "toll", "major", "standard"}
        
        for feature in data["features"]:
            road_type = feature["properties"].get("road_type")
            assert road_type in valid_types


class TestSimulateEndpoint:
    """Test GET /api/simulate evacuation simulation."""
    
    def test_simulate_default_parameters(self):
        """Test simulation with default parameters."""
        with patch("app.api.routes.EvacuationService") as MockService:
            import networkx as nx
            # Configure mock instance
            service_instance = MockService.return_value
            
            # Create a simple valid graph for the endpoint logic to use
            mock_graph = nx.DiGraph()
            mock_graph.add_edge(1, 2)
            service_instance.generate_network_graph.return_value = mock_graph
            
            service_instance.calculate_max_flow.return_value = 5000
            
            response = client.get("/simulate")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify response structure
            assert "scenario" in data
            assert data["max_throughput_vph"] == 5000

    def test_simulate_invalid_scenario_handled(self):
        """Test that invalid scenario is handled gracefully."""
        with patch("app.api.routes.EvacuationService") as MockService:
            import networkx as nx
            service_instance = MockService.return_value
            
            mock_graph = nx.DiGraph()
            mock_graph.add_edge(1, 2)
            service_instance.generate_network_graph.return_value = mock_graph
            
            service_instance.calculate_max_flow.return_value = 5000
            
            response = client.get("/simulate?scenario=invalid_scenario")
            
            # Should not crash - return 200 with default or handled result
            assert response.status_code == 200

class TestScenariosEndpoint:
    """Test GET /api/scenarios endpoint."""
    
    def test_scenarios_returns_json(self):
        """Test that endpoint returns valid JSON."""
        response = client.get("/scenarios")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
    
    def test_scenarios_structure(self):
        """Test that response has correct structure."""
        response = client.get("/scenarios")
        data = response.json()
        
        assert "scenarios" in data
        assert isinstance(data["scenarios"], list)



class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_invalid_endpoint_returns_404(self):
        """Test that invalid endpoint returns 404."""
        response = client.get("/nonexistent")
        
        assert response.status_code == 404
    
    def test_simulate_invalid_scenario_handled(self):
        """Test that invalid scenario is handled gracefully."""
        # Should either return 404 or use default
        response = client.get("/simulate?scenario=invalid_scenario")
        
        # Should not crash - either 404 or defaults to baseline
        assert response.status_code in [200, 404]
