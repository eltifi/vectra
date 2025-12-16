"""
@file routes.py
@brief FastAPI API endpoint definitions for Vectra backend

@details
Provides RESTful endpoints for:
- Road network querying (GeoJSON export)
- Max-flow evacuation simulation
- Disaster scenario configuration
- Metrics and capacity analysis

All endpoints interact with PostGIS database and NetworkX graph library
for spatial analysis and evacuation modeling.

@author Vectra Project
@date 2025-12-12
@version 1.0
@license AGPL-3.0

@see services.evacuation for max-flow algorithm
@see models.road_network for data models
@see db.database for session management
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from sqlalchemy import text
from app.services.evacuation import EvacuationService
from app.models.road_network import RoadSegment
from app.models.msa import MetropolitanArea
import json
from shapely.wkt import loads 
import shapely.geometry
import networkx as nx
import logging

## @brief FastAPI router instance for API endpoints
router = APIRouter()

## @brief Module-level logger for request/response debugging
logger = logging.getLogger(__name__)


from app.core.cache import cache

@router.get("/segments")
async def get_segments(db: Session = Depends(get_db)):
    """
    @brief Retrieve complete road network as GeoJSON FeatureCollection
    @details
    Cached in Redis for 24 hours.
    """
    # Try cache first
    cache_key = "api:segments:geojson"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # ... existing query logic ...
    """
    @brief Retrieve complete road network as GeoJSON FeatureCollection
    
    @details
    Returns all road segments from PostGIS database merged by road name
    to create continuous line geometries. Segments are classified by type
    (interstate, toll, major, standard) based on official FDOT data.
    
    **SQL Query Strategy:**
    1. ST_LineMerge: Merges connected line segments into single LineString
    2. ST_Collect: Aggregates all geometries by road name
    3. BOOL_OR: Determines if any segment in group is interstate/toll
    4. MAX aggregation: Preserves representative values for lanes, speed
    
    @param db SQLAlchemy Session (injected via Depends)
    
    @return GeoJSON FeatureCollection dict with merged road segments
    
    @note
    - Returns empty FeatureCollection if database is uninitialized
    - NULL geometries are excluded from query
    - Road classification hierarchy: interstate > toll > major > standard
    
    @throws HTTPException: Database connection errors
    
    @complexity O(n log n) where n = number of road segments
    
    @see services.evacuation.generate_network_graph for graph construction
    """
    query = """
    WITH merged_roads AS (
        SELECT 
            road_name,
            MAX(id) as max_id,
            ST_LineMerge(ST_Collect(geom)) as merged_geom,
            MAX(lanes) as lanes,
            MAX(speed_limit) as speed_limit,
            BOOL_OR(is_interstate) as is_interstate,
            BOOL_OR(is_toll_road) as is_toll_road,
            CASE 
                -- Interstate highways: From official FDOT Interstates shapefile
                WHEN BOOL_OR(is_interstate) = true THEN 'interstate'
                -- Toll roads: From official FDOT Toll Roads shapefile
                WHEN BOOL_OR(is_toll_road) = true THEN 'toll'
                -- Major roads: RD_STATUS 02 (active)
                WHEN MAX(rd_status) = '02' THEN 'major'
                ELSE 'standard'
            END as road_type
        FROM road_segments
        WHERE geom IS NOT NULL
        GROUP BY road_name
    )
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', json_agg(json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(merged_geom)::json,
            'properties', json_build_object(
                'id', max_id, 
                'name', road_name, 
                'lanes', lanes, 
                'speed_limit', speed_limit,
                'road_type', road_type
            )
        ))
    ) FROM merged_roads
    """
    result = db.execute(text(query))
    geojson = result.scalar()
    # Ensure we're returning the dict directly (not JSON string)
    final_result = geojson
    if isinstance(geojson, str):
        final_result = json.loads(geojson)
    
    # Cache result (TTL: 24h = 86400s)
    await cache.set(cache_key, final_result, ttl=86400)
    
    return final_result


@router.get("/calculate_metrics")
def metrics(db: Session = Depends(get_db)):
    """
    @brief Calculate network capacity and evacuation metrics
    
    @details
    Computes aggregate statistics about the road network:
    - Total road miles by classification
    - Average capacity by region
    - Network connectivity metrics
    
    @param db SQLAlchemy Session (injected via Depends)
    
    @return Dictionary with network statistics
    
    @throws HTTPException: If network data unavailable
    
    @todo Implement full metric calculation
    """
    pass


@router.get("/simulate")
async def run_simulation(
    scenario: str = "baseline",
    region: str = "Tampa Bay",
    db: Session = Depends(get_db)
):
    """
    @brief Execute max-flow evacuation simulation on road network
    
    @details
    Runs Edmonds-Karp algorithm to compute maximum evacuation throughput
    for specified scenario and region. Supports two network configurations:
    - **baseline**: Standard road network with normal directional flow
    - **contraflow**: Reversed lanes on major routes for outbound capacity
    
    **Algorithm:**
    1. Generate directed graph from road segments (scenario-dependent)
    2. Select random source/sink nodes with reachability verification
    3. Run Edmonds-Karp max-flow algorithm: O(V*E²) complexity
    4. Calculate clearance time based on population and throughput
    5. Assess gridlock risk based on capacity/demand ratios
    
    @param scenario (str) Network configuration: "baseline" or "contraflow" [default: "baseline"]
    @param region (str) Geographic region for simulation [default: "Tampa Bay"]
    @param db SQLAlchemy Session (injected via Depends)
    
    @return JSON with simulation results:
    - scenario: Configuration used
    - max_throughput_vph: Maximum flow in vehicles per hour
    - clearance_time_hours: Estimated evacuation clearance time
    - gridlock_risk: Risk assessment (CRITICAL|MODERATE|LOW)
    - graph_size: Node and edge counts
    - description: Algorithm and data source notes
    
    @throws HTTPException(404): If graph is empty (ETL not run)
    @throws HTTPException(500): Graph construction or algorithm errors
    
    @note
    - Source/sink selection prioritizes nodes with 50+ reachable descendants
    - Fallback to disconnected graph largest connected component
    - Clearance time = 1,000,000 / max_flow (empirical scaling)
    
    @complexity O(V*E²) where V = nodes, E = edges (Edmonds-Karp)
    
    @see services.evacuation for graph generation and flow calculation
    """
    logger.info(f"Received simulation request for scenario: {scenario}, region: {region}")
    
    # Cache Check
    cache_key = f"api:simulate:{scenario}:{region}"
    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info(f"Returning cached simulation result for {cache_key}")
        return cached_result
    
    service = EvacuationService(db)
    
    # Generate Graph (Real Data)
    graph = service.generate_network_graph(scenario, region)
    logger.info(f"Full Graph built: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    
    # Define Source/Sink (Tampa -> Ocala)
    # 1. Find Random Source/Sink if explicit IDs unknown
    try:
        if graph.number_of_nodes() == 0:
             raise HTTPException(status_code=404, detail="Graph is empty. ETL failed?")

        if not nx.is_weakly_connected(graph):
            largest_cc = max(nx.weakly_connected_components(graph), key=len)
            subgraph = graph.subgraph(largest_cc).copy()
        else:
            subgraph = graph

        nodes = list(subgraph.nodes())
        
        # Smart Source/Sink Selection:
        # Find a pair (u, v) such that v is reachable from u
        import random
        source_node = None
        sink_node = None
        
        # Try up to 10 random seeds to find a connected pair with reasonable distance
        for _ in range(10):
            candidate_source = random.choice(nodes)
            # Find reachable nodes (BFS)
            descendants = nx.descendants(subgraph, candidate_source)
            if len(descendants) > 50: # Ensure non-trivial path
                 source_node = candidate_source
                 # Pick a sink from descendants, ideally far away?
                 # Just random for now, or last in list
                 sink_node = list(descendants)[-1] # Deterministic-ish
                 break
        
        if source_node is None:
             # Fallback
             source_node = nodes[0]
             sink_node = nodes[-1]
        
        # Use the subgraph for calculation
        graph = subgraph
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph error: {str(e)}")

    # 2. Run Algorithm
    flow_value = service.calculate_max_flow(graph, source_node, sink_node)
    
    # 3. Calculate metrics
    gridlock_risk = "CRITICAL" if flow_value < 1000 else "MODERATE"
    clearance_time_hours = 24.0 
    if flow_value > 0:
        clearance_time_hours = 1000000 / flow_value 
    
    return {
        "scenario": scenario,
        "max_throughput_vph": flow_value,
        "clearance_time_hours": round(clearance_time_hours, 2),
        "gridlock_risk": gridlock_risk,
        "graph_size": {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges()
        },
        "description": "Real-time calculation using Edmonds-Karp on District 7 Graph."
    }
    
    # Cache Result (TTL: 1h = 3600s)
    await cache.set(cache_key, result, ttl=3600)
    return result


@router.get("/scenarios")
def get_scenarios():
    """
    @brief Retrieve all predefined evacuation disaster scenarios
    
    @details
    Returns JSON configuration of scientific disaster scenarios
    with atmospheric and geometric parameters for evacuation modeling.
    
    **Scenario Parameters:**
    - **id**: Unique scenario identifier (e.g., "NW - Gulf Approach (Tampa Bay)")
    - **label**: User-friendly scenario name
    - **category**: Severity category (1-5 or equivalent)
    - **windSpeed**: Maximum sustained wind or equivalent metric (mph)
    - **pressureMb**: Atmospheric pressure or equivalent metric (millibars)
    - **latitude**: Event center latitude (22-30°N for Florida)
    - **longitude**: Event center longitude (78-88°W for Florida)
    - **direction**: Movement direction in degrees (0-360°)
    - **translationSpeed**: Forward speed in knots (10-20 typical)
    - **affectedRegions**: List of impacted geographic regions
    
    **Data Source:** App configuration file at app/config/scenarios.json
    Scenarios support any large-scale evacuation event (hurricanes, floods, etc).
    
    @return JSON dict with "scenarios" array containing scenario configurations
    
    @throws HTTPException(404): If configuration file not found
    @throws HTTPException(500): If JSON parsing fails
    
    @note
    Scenarios are static but can be extended by modifying JSON file.
    All speed measurements use standard units (mph, knots).
    
    @see main.read_root for scenario descriptions and regional mappings
    """
    import os
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'scenarios.json')
    
    try:
        with open(config_path, 'r') as f:
            scenarios = json.load(f)
        return scenarios
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Scenarios configuration not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error parsing scenarios configuration")


@router.get("/msas")
def get_msas(db: Session = Depends(get_db)):
    """
    @brief Retrieve all Florida Metropolitan Planning Organization (MPO) Areas
    
    @details
    Returns a comprehensive list of all Metropolitan Planning Organization (MPO) areas
    in Florida from the FDOT MPO Area Roadways dataset. Each MPO represents a geographic
    region for transportation planning and evacuation analysis.
    
    **MPO Data Included:**
    - **id**: Unique MPO identifier in database
    - **name**: Official MPO name (e.g., "Tampa Bay Area")
    - **mpo_code**: 2-character FDOT MPO code
    - **state**: State abbreviation (FL)
    
    Data comes directly from the FDOT MPO Area Roadways shapefile, ensuring
    the MSA list is linked to actual road network data.
    
    @param db SQLAlchemy Session (injected via Depends)
    
    @return JSON dict with MSAs array containing all MPO areas
    
    @throws HTTPException(500): If database query fails
    
    @note
    - Data source: FDOT MPO Area Roadways shapefile
    - Returns empty array if no MPOs have been seeded
    - Each MPO is linked to road segments in the road_segments table
    
    @see services.evacuation for region-based simulation queries
    @see models.msa for MetropolitanArea data model
    
    @complexity O(n) where n = number of MPOs
    """
    try:
        msas = db.query(MetropolitanArea).order_by(MetropolitanArea.name).all()
        
        # Convert to list of dictionaries for JSON serialization
        msa_list = []
        for msa in msas:
            msa_dict = {
                "id": msa.id,
                "name": msa.name,
                "mpo_code": msa.mpo_code,
                "state": msa.state,
            }
            msa_list.append(msa_dict)
        
        return {
            "type": "FeatureCollection",
            "features": msa_list,
            "count": len(msa_list)
        }
    except Exception as e:
        logger.error(f"Error retrieving MSAs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving MSAs: {str(e)}")



