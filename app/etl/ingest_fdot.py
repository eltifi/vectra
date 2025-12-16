"""
FDOT Data ETL (Extract, Transform, Load) Module

This module implements the complete ETL pipeline for processing FDOT (Florida Department of Transportation)
public geospatial data into the PostGIS database. The pipeline:

1. EXTRACT: Loads shapefiles from the raw data directory
2. TRANSFORM: Aggregates attributes, calculates derived fields, integrates official classifications
3. LOAD: Populates PostGIS database with processed features

Data Sources:
- basemap_route_road.shp: Complete road network centerline inventory
- number_of_lanes.shp: Lane count attribute data
- maxspeed.shp: Posted speed limit data
- interstates/interstates.shp: Official FDOT interstate highway classifications
- toll_roads/toll_roads.shp: Official FDOT toll road classifications

Processing Workflow:
1. Load geometric data from shapefiles
2. Aggregate lanes and speed data by road ID
3. Reproject to WGS84 (EPSG:4326)
4. Calculate geometric properties (length, direction)
5. Calculate network properties (capacity, travel time)
6. Classify roads using official FDOT datasets
7. Synthesize UI-friendly road names
8. Ingest into PostGIS with spatial indexing
9. Build pgRouting network topology

Author: Vectra Project
License: AGPL-3.0
"""

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
from geoalchemy2 import Geometry, WKTElement
import os
from shapely.geometry import LineString, Point
import shapely.wkt
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Database Connection String
# Environment variable allows override, with local Docker default
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:mysecretpassword@localhost:5432/vectra"
)
engine = create_engine(DATABASE_URL)

# Raw data directory path
# In Docker: /app/data
# Local development: adjust path as needed
RAW_DATA_PATH = "/app/data"


def load_data(filename: str) -> gpd.GeoDataFrame or None:
    """
    Load a shapefile from the raw data directory.
    
    Handles both flat file structures and nested subdirectories.
    For example: "maxspeed.shp" or "interstates/interstates.shp"
    
    Args:
        filename (str): Relative path to shapefile (with .shp extension)
        
    Returns:
        gpd.GeoDataFrame: Loaded geospatial dataframe or None if file not found
        
    Raises:
        Exception: If file cannot be read (corrupt file, invalid format)
    """
    # Try direct path first
    file_path = os.path.join(RAW_DATA_PATH, filename)
    
    if not os.path.exists(file_path):
        # Try as nested subdirectory
        folder_name = os.path.splitext(filename)[0]
        file_path = os.path.join(RAW_DATA_PATH, folder_name, filename)
        
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {filename}")
            return None
    
    logger.info(f"Loading shapefile: {filename}")
    try:
        gdf = gpd.read_file(file_path)
        logger.info(f"  → Loaded {len(gdf)} features")
        return gdf
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}")
        return None


def aggregate_attributes(routes: gpd.GeoDataFrame, 
                        lanes: gpd.GeoDataFrame or None,
                        speed: gpd.GeoDataFrame or None) -> gpd.GeoDataFrame:
    """
    Aggregate attribute data (lanes, speed) with base routes.
    
    FDOT data often stores attributes in separate shapefiles. This function
    merges them with the main routes data using 'ROADWAY' as the common key.
    Missing values are filled with defaults.
    
    Args:
        routes (gpd.GeoDataFrame): Base route geometry
        lanes (gpd.GeoDataFrame): Lane count data (optional)
        speed (gpd.GeoDataFrame): Speed limit data (optional)
        
    Returns:
        gpd.GeoDataFrame: Routes with aggregated attributes
    """
    logger.info("Aggregating attribute data...")
    
    # Aggregate lanes by road identifier
    if lanes is not None:
        lanes_agg = lanes.groupby('ROADWAY')['LANE_CNT'].max().reset_index()
        routes = routes.merge(lanes_agg, on='ROADWAY', how='left')
        routes['LANE_CNT'] = routes['LANE_CNT'].fillna(1)
        logger.info(f"  → Merged lane data for {routes['LANE_CNT'].notna().sum()} roads")
    else:
        routes['LANE_CNT'] = 1

    # Aggregate speed limits by road identifier
    if speed is not None:
        speed_agg = speed.groupby('ROADWAY')['SPEED'].max().reset_index()
        routes = routes.merge(speed_agg, on='ROADWAY', how='left')
        routes['SPEED'] = routes['SPEED'].fillna(30)
        logger.info(f"  → Merged speed data for {routes['SPEED'].notna().sum()} roads")
    else:
        routes['SPEED'] = 30

    return routes


def reproject_and_clean(routes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Reproject to WGS84 and remove invalid geometries.
    
    All data must be in EPSG:4326 (WGS84) for consistency with PostGIS.
    Invalid geometries (null, empty) are excluded before processing.
    
    Args:
        routes (gpd.GeoDataFrame): Routes with various projections
        
    Returns:
        gpd.GeoDataFrame: Clean routes in WGS84
    """
    logger.info("Reprojecting and cleaning geometry...")
    
    # Ensure WGS84 coordinate system
    if routes.crs != "EPSG:4326":
        logger.info(f"  → Reprojecting from {routes.crs} to EPSG:4326")
        routes = routes.to_crs("EPSG:4326")
    
    # Remove null geometries
    initial_count = len(routes)
    routes = routes[routes.geometry.notnull()]
    removed = initial_count - len(routes)
    if removed > 0:
        logger.warning(f"  → Removed {removed} features with null geometry")
    
    return routes


def calculate_geometric_properties(routes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Calculate length and other geometric properties.
    
    Length is calculated in UTM projected coordinates (meters) for accuracy,
    then results are stored for use in network analysis.
    
    Args:
        routes (gpd.GeoDataFrame): WGS84 routes
        
    Returns:
        gpd.GeoDataFrame: Routes with length_m column
    """
    logger.info("Calculating geometric properties...")
    
    # Project to local UTM for accurate length calculation
    routes_utm = routes.to_crs(routes.estimate_utm_crs())
    routes['length_m'] = routes_utm.length
    
    logger.info(f"  → Average segment length: {routes['length_m'].mean():.2f}m")
    
    return routes


def calculate_network_properties(routes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Calculate network physics properties for evacuation simulation.
    
    Capacity Calculation:
    - vph = lanes × 1800 vehicles/hour/lane (HCM standard)
    - Based on FDOT lane counts
    
    Travel Time Calculation:
    - cost_time = distance (m) / speed (m/s)
    - Converts speed from mph to m/s
    - Used for Edmonds-Karp max flow algorithm
    
    Args:
        routes (gpd.GeoDataFrame): Routes with lanes, speed, length
        
    Returns:
        gpd.GeoDataFrame: Routes with capacity and cost_time
    """
    logger.info("Calculating network properties...")
    
    # Capacity = lanes × HCM standard (1800 vph per lane)
    routes['capacity'] = routes['LANE_CNT'] * 1800
    
    # Convert speed from mph to m/s
    # 1 mph = 0.44704 m/s
    conversion_factor = 0.44704
    routes['speed_ms'] = routes['SPEED'] * conversion_factor
    
    # Replace any zero speeds (invalid) with minimum default
    routes['speed_ms'] = routes['speed_ms'].replace(0, 10 * conversion_factor)
    
    # Cost = travel time = distance / speed (in seconds)
    routes['cost_time'] = routes['length_m'] / routes['speed_ms']
    
    logger.info(f"  → Average capacity: {routes['capacity'].mean():.0f} vph")
    logger.info(f"  → Average travel time: {routes['cost_time'].mean():.1f}s")
    
    return routes


def identify_official_classifications(routes: gpd.GeoDataFrame,
                                     interstates: gpd.GeoDataFrame or None,
                                     toll_roads: gpd.GeoDataFrame or None) -> gpd.GeoDataFrame:
    """
    Identify interstates and toll roads using official FDOT shapefiles.
    
    This is the most reliable method for road classification, using
    authoritative FDOT datasets rather than heuristic rules.
    
    Args:
        routes (gpd.GeoDataFrame): Base routes
        interstates (gpd.GeoDataFrame): Official FDOT interstates
        toll_roads (gpd.GeoDataFrame): Official FDOT toll roads
        
    Returns:
        gpd.GeoDataFrame: Routes with is_interstate and is_toll_road flags
    """
    logger.info("Identifying interstates and toll roads...")
    
    # Create lookup sets from official FDOT datasets
    interstate_roadways = set()
    if interstates is not None:
        interstate_roadways = set(interstates['ROADWAY'].unique())
        logger.info(f"  → {len(interstate_roadways)} interstate road IDs found")
    
    toll_road_roadways = set()
    if toll_roads is not None:
        toll_road_roadways = set(toll_roads['ROADWAY'].unique())
        logger.info(f"  → {len(toll_road_roadways)} toll road IDs found")
    
    # Flag roads in the official datasets
    routes['is_interstate'] = routes['ROADWAY'].isin(interstate_roadways)
    routes['is_toll_road'] = routes['ROADWAY'].isin(toll_road_roadways)
    
    logger.info(f"  → {routes['is_interstate'].sum()} interstate segments")
    logger.info(f"  → {routes['is_toll_road'].sum()} toll road segments")
    
    return routes


def synthesize_road_names(routes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Create UI-friendly road names for visualization.
    
    Names are synthesized from ROADWAY identifiers with classification suffixes.
    This is used for display in the frontend application.
    
    Args:
        routes (gpd.GeoDataFrame): Routes with classification flags
        
    Returns:
        gpd.GeoDataFrame: Routes with road_name column
    """
    logger.info("Synthesizing road names...")
    
    # Start with road identifier
    routes['road_suffix'] = ''
    
    # Add classification suffixes
    routes.loc[routes['is_interstate'], 'road_suffix'] = ' (Major Hwy)'
    routes.loc[routes['is_toll_road'], 'road_suffix'] = ' (Toll)'
    
    # Concatenate for final names
    routes['road_name'] = routes['ROADWAY'].astype(str) + routes['road_suffix']
    
    return routes


def prepare_for_database(routes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Prepare final dataframe for database ingestion.
    
    Selects required columns, renames to match database schema,
    assigns sequential IDs, and ensures data types are correct.
    
    Args:
        routes (gpd.GeoDataFrame): Processed routes
        
    Returns:
        gpd.GeoDataFrame: Ready for to_postgis()
    """
    logger.info("Preparing data for database ingestion...")
    
    # Select columns matching database schema
    columns_map = {
        'geometry': 'geom',
        'LANE_CNT': 'lanes',
        'SPEED': 'speed_limit',
        'RD_STATUS': 'rd_status'
    }
    
    output_gdf = routes[list(columns_map.keys()) + 
                       ['length_m', 'capacity', 'cost_time', 'is_interstate', 
                        'is_toll_road', 'road_name']].copy()
    
    # Rename columns to match schema
    output_gdf = output_gdf.rename(columns=columns_map)
    
    # Set geometry column
    output_gdf.set_geometry('geom', inplace=True)
    
    # Assign sequential IDs
    output_gdf = output_gdf.reset_index(drop=True)
    output_gdf['id'] = output_gdf.index + 1
    
    logger.info(f"  → {len(output_gdf)} segments ready for ingestion")
    
    return output_gdf


def ingest_to_postgis(output_gdf: gpd.GeoDataFrame) -> bool:
    """
    Ingest processed road data into PostGIS database.
    
    Writes GeoDataFrame to road_segments table with:
    - LINESTRING geometry type
    - WGS84 (EPSG:4326) coordinate system
    - Replace mode (drop existing table)
    - Spatial index creation
    
    Args:
        output_gdf (gpd.GeoDataFrame): Processed data ready for storage
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Ingesting data into PostGIS...")
    
    try:
        output_gdf.to_postgis(
            "road_segments",
            engine,
            if_exists='replace',  # Drop and recreate table
            index=False,
            dtype={'geom': Geometry('LINESTRING', srid=4326)}
        )
        logger.info(f"  → {len(output_gdf)} segments ingested successfully")
        return True
    except Exception as e:
        logger.error(f"Error during PostGIS ingestion: {e}")
        return False


def set_primary_key() -> bool:
    """
    Set primary key constraint on road_segments table.
    
    Required for pgRouting topology creation and efficient indexing.
    
    Returns:
        bool: True if successful
    """
    logger.info("Setting primary key constraint...")
    
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE road_segments ADD PRIMARY KEY (id);"))
        logger.info("  → Primary key set successfully")
        return True
    except Exception as e:
        logger.warning(f"Primary key may already exist: {e}")
        return True  # Not critical if already exists


def build_network_topology() -> bool:
    """
    Build pgRouting network topology.
    
    Creates source/target nodes for the road network graph required by
    pgRouting algorithms (Dijkstra, Edmonds-Karp, etc).
    
    The topology connects road segments to form a routable network.
    Tolerance (0.001 degrees) is used to snap nearby segment endpoints.
    
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Building network topology with pgRouting...")
    
    try:
        with engine.begin() as conn:
            # Ensure columns exist
            conn.execute(text("ALTER TABLE road_segments ADD COLUMN IF NOT EXISTS source integer;"))
            conn.execute(text("ALTER TABLE road_segments ADD COLUMN IF NOT EXISTS target integer;"))
            
            # Create topology
            # Tolerance: 0.001 degrees ≈ 111 meters (adequate for Florida)
            logger.info("  → Creating topology with pgr_createTopology...")
            conn.execute(text("SELECT pgr_createTopology('road_segments', 0.001, 'geom', 'id');"))
            
        logger.info("  → Network topology built successfully")
        return True
    except Exception as e:
        logger.error(f"Error building topology: {e}")
        return False


def run_etl() -> bool:
    """
    Execute the complete ETL pipeline.
    
    Orchestrates all ETL steps:
    1. Load source data from shapefiles
    2. Aggregate attributes
    3. Clean and reproject geometry
    4. Calculate properties
    5. Classify roads
    6. Prepare for database
    7. Ingest to PostGIS
    8. Build network topology
    
    Returns:
        bool: True if entire pipeline succeeds, False if any step fails
        
    Raises:
        SystemExit: Aborts if critical data missing (routes)
    """
    logger.info("=" * 70)
    logger.info("STARTING FDOT DATA ETL PIPELINE")
    logger.info("=" * 70)

    # STEP 1: EXTRACT - Load source shapefiles
    logger.info("\n[STEP 1] EXTRACT - Loading source data...")
    routes = load_data("basemap_route_road.shp")
    lanes = load_data("number_of_lanes.shp")
    speed = load_data("maxspeed.shp")
    interstates = load_data("interstates/interstates.shp")
    toll_roads = load_data("toll_roads/toll_roads.shp")
    
    # Load optional attribute data
    functional_class = load_data("functional_classification.shp")
    road_status = load_data("road_status.shp")
    aadt = load_data("aadt.shp")
    rest_areas = load_data("rest_areas.shp")
    
    # Abort if critical data missing
    if routes is None:
        logger.critical("CRITICAL ERROR: Routes file missing. Aborting ETL.")
        return False

    # STEP 2: TRANSFORM - Aggregate and process data
    logger.info("\n[STEP 2] TRANSFORM - Processing data...")
    routes = aggregate_attributes(routes, lanes, speed)
    routes = reproject_and_clean(routes)
    routes = calculate_geometric_properties(routes)
    routes = calculate_network_properties(routes)
    routes = identify_official_classifications(routes, interstates, toll_roads)
    routes = synthesize_road_names(routes)
    
    # STEP 3: LOAD - Ingest into database
    logger.info("\n[STEP 3] LOAD - Ingesting into database...")
    output_gdf = prepare_for_database(routes)
    
    if not ingest_to_postgis(output_gdf):
        return False
    
    if not set_primary_key():
        return False
    
    # STEP 4: POST-PROCESSING - Build topology
    logger.info("\n[STEP 4] POST-PROCESSING - Building topology...")
    if not build_network_topology():
        return False

    logger.info("\n" + "=" * 70)
    logger.info("✓ ETL PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("=" * 70)
    return True


if __name__ == "__main__":
    # Allow standalone execution for testing/debugging
    success = run_etl()
    exit(0 if success else 1)
