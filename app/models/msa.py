"""
Metropolitan Statistical Area (MSA) Data Model

This module defines the SQLAlchemy ORM model for Florida Metropolitan Statistical Areas.
Each MSA represents a geographic area with demographic, economic, and infrastructure data.

Model: MetropolitanArea
- Stores MSA boundaries as polygon geometries (PostGIS)
- Maintains population and demographic statistics
- Tracks key metrics for evacuation planning
- Links to associated road network segments

Key Attributes:
- geom: WGS84 polygon geometry (EPSG:4326)
- name: Official MSA name
- population: Total population in MSA
- area_sq_miles: Geographic area in square miles
- counties: Associated counties

Author: Vectra Project
License: AGPL-3.0
"""

from sqlalchemy import Column, Integer, Float, String
from geoalchemy2 import Geometry
from app.db.base import Base


class MetropolitanArea(Base):
    """
    SQLAlchemy ORM model for Metropolitan Planning Organization (MPO) Areas.
    
    MPOs are the official geographic/administrative regions in Florida for transportation
    planning and evacuation analysis. Data comes from FDOT's MPO Area Roadways shapefile.
    
    Attributes:
        id (int): Unique MPO identifier, primary key
        name (str): Official MPO name (e.g., "Tampa Bay Area")
        mpo_code (str): 2-character FDOT MPO code
        state (str): State abbreviation (FL for Florida)
    """
    
    __tablename__ = "metropolitan_areas"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # MPO Identification
    name = Column(String(255), unique=True, nullable=False, index=True)
    mpo_code = Column(String(2), unique=True, nullable=False, index=True)
    state = Column(String(2), default="FL")
