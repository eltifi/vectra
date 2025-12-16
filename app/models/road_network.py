"""
Road Network Data Model

This module defines the SQLAlchemy ORM model for road network segments stored in PostGIS.
Each road segment represents a portion of the transportation network with geometric
and attribute data required for evacuation analysis.

Model: RoadSegment
- Stores linearized road geometry (LINESTRING)
- Maintains topological relationships (source/target nodes)
- Tracks road classification (interstate, toll, major, standard)
- Stores capacity, cost, and directionality information

Key Attributes:
- geom: WGS84 geographic linestring geometry (EPSG:4326)
- source/target: pgRouting network topology IDs
- lanes, speed_limit, capacity: Road infrastructure attributes
- is_interstate, is_toll_road: Official FDOT classification flags
- rd_status: FDOT RCI (Road Centerline Inventory) status code

Author: Vectra Project
License: AGPL-3.0
"""

from sqlalchemy import Column, Integer, Float, Boolean, String
from geoalchemy2 import Geometry
from app.db.base import Base
class RoadSegment(Base):
    """
    SQLAlchemy ORM model for road network segments.
    
    This class represents individual road segments in the transportation network.
    Segments are loaded from FDOT public shapefiles and stored in PostGIS
    with full topological relationships for network analysis.
    
    Attributes:
        id (int): Unique segment identifier, primary key
        geom (Geometry): WGS84 linestring geometry of road segment
        source (int): Starting node ID in pgRouting topology
        target (int): Ending node ID in pgRouting topology
        length_m (float): Length of segment in meters
        lanes (int): Number of lanes
        speed_limit (int): Posted speed limit in mph
        capacity (float): Evacuation capacity in vehicles per hour (vph)
        cost_time (float): Travel time in seconds
        is_one_way (bool): Whether road is one-directional
        road_name (str): Display name for UI visualization
        direction (str): Cardinal direction (NB, SB, EB, WB)
        rd_status (str): FDOT RCI status code (02=major, 09=interstate, etc.)
        is_interstate (bool): True if from official FDOT Interstates shapefile
        is_toll_road (bool): True if from official FDOT Toll Roads shapefile
    """
    
    __tablename__ = "road_segments"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Geometry Column (PostGIS)
    # LINESTRING: represents road as a line from start to end point
    # SRID 4326: WGS84 coordinate system (latitude/longitude)
    geom = Column(Geometry("LINESTRING", srid=4326))
    
    # Network Topology (pgRouting standard)
    # source and target reference nodes in the road network graph
    source = Column(Integer, index=True)  # Starting node ID
    target = Column(Integer, index=True)  # Ending node ID
    
    # Road Geometry and Infrastructure
    length_m = Column(Float)              # Length in meters
    lanes = Column(Integer)               # Number of lanes (affects capacity)
    speed_limit = Column(Integer)         # Posted speed limit (mph)
    capacity = Column(Float)              # Evacuation capacity (vehicles/hour)
    cost_time = Column(Float)             # Travel time cost (seconds)
    
    # Road Directional Properties
    is_one_way = Column(Boolean, default=False)  # One-way restriction flag
    direction = Column(String, nullable=True)    # Cardinal direction (NB/SB/EB/WB)
    
    # Road Identification
    road_name = Column(String, nullable=True)    # Name for UI display
    
    # FDOT Classification Data
    # RD_STATUS: FDOT Road Centerline Inventory status codes
    #   02/06/07 = Major highways
    #   09 = Interstate highways (active)
    #   12 = Interstate combinations
    rd_status = Column(String, nullable=True)
    
    # Official FDOT Shapefile Flags
    # These flags indicate road source from authoritative FDOT datasets
    is_interstate = Column(Boolean, default=False)  # From official FDOT Interstates dataset
    is_toll_road = Column(Boolean, default=False)   # From official FDOT Toll Roads dataset
    
    # FDOT Advanced Attributes
    # Functional classification for road hierarchy
    functional_class = Column(String, nullable=True)  # FC01=Interstate, FC02=US Hwy, etc.
    
    # Highway Performance Monitoring System (HPMS) data
    hpms_key = Column(String, nullable=True)        # HPMS record key identifier
    
    # Federal-Aid Highway System classification
    fed_aid_primary = Column(Boolean, default=False)  # Primary federal-aid route
    fed_aid_secondary = Column(Boolean, default=False)  # Secondary federal-aid route
    
    # Road Status and Condition
    road_status = Column(String, nullable=True)     # Road condition status code
    
    # Annual Average Daily Traffic (AADT)
    aadt = Column(Integer, nullable=True)           # Annual average daily traffic count


class RestArea(Base):
    """
    SQLAlchemy ORM model for rest areas and welcome centers.
    
    Rest areas serve as potential staging and evacuation assembly points.
    
    Attributes:
        id (int): Unique rest area identifier, primary key
        geom (Geometry): WGS84 point geometry of rest area location
        name (str): Name of rest area/welcome center
        facility_type (str): Type (rest area, welcome center, etc.)
        interstate (str): Associated interstate(s)
        direction (str): Direction of facility (NB, SB, EB, WB)
        state (str): State (FL for Florida)
    """
    
    __tablename__ = "rest_areas"
    
    id = Column(Integer, primary_key=True, index=True)
    geom = Column(Geometry("POINT", srid=4326), index=True)
    name = Column(String, nullable=True)
    facility_type = Column(String, nullable=True)
    interstate = Column(String, nullable=True)
    direction = Column(String, nullable=True)
    state = Column(String, default="FL")