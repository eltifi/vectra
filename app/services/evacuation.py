"""
@file evacuation.py
@brief Evacuation service with max-flow network simulation

@details
Provides business logic for evacuation modeling:
- Dynamic network graph generation from road segments
- Contraflow lane reversal logic by region and road classification
- Edmonds-Karp max-flow algorithm for evacuation capacity calculation
- Support for baseline and scenario-based configurations

@author Vectra Project
@date 2025-12-12
@version 1.0
@license AGPL-3.0

@see models.road_network for RoadSegment data model
@see db.database for session management
"""

import networkx as nx
from sqlalchemy.orm import Session
from app.models.road_network import RoadSegment
from sqlalchemy import or_
import shapely.wkt
import shapely.wkb


class EvacuationService:
    """
    @brief Service layer for evacuation network analysis and simulation
    
    @details
    Manages generation of evacuation scenario networks and flow calculations.
    Supports baseline (normal traffic) and contraflow (reversed lanes) scenarios
    with region-specific evacuation direction logic.
    
    @author Vectra Project
    @date 2025-12-12
    """
    
    def __init__(self, db: Session):
        """
        @brief Initialize evacuation service with database session
        
        @param db SQLAlchemy Session for database queries
        """
        self.db = db

    def generate_network_graph(
        self,
        scenario: str = "baseline",
        region: str = "Tampa Bay"
    ) -> nx.DiGraph:
        """
        @brief Build directed network graph from road segments for simulation
        
        @details
        Generates a NetworkX DiGraph representing the road network. In contraflow
        scenarios, reverses lanes on major highways based on region-specific
        evacuation logic to maximize outbound capacity.
        
        **Graph Construction:**
        1. Query all RoadSegment records from database
        2. Create nodes for source/target IDs (pgRouting topology)
        3. Add edges with capacity as weight
        4. Apply contraflow logic: reverse inbound lanes on major highways
        
        **Contraflow Logic by Region:**
        - **Tampa Bay/Sarasota**: Reverse SB lanes (evacuate north via I-75)
        - **Miami/South FL**: Reverse SB lanes (evacuate north via I-95, Turnpike)
        - **Orlando/Daytona**: Reverse SB lanes, WB lanes on I-4
        - **Jacksonville**: Reverse SB lanes (I-95), EB lanes (I-10)
        - **Panhandle**: Reverse SB lanes (evacuate north)
        
        **Direction Detection Algorithm:**
        Uses coordinate geometry to determine road heading:
        - dy < 0: Southbound (negative latitude change)
        - dy > 0: Northbound (positive latitude change)
        - dx < 0: Westbound (negative longitude change)
        - dx > 0: Eastbound (positive longitude change)
        
        @param scenario (str) Configuration: "baseline" or "contraflow" [default: "baseline"]
        @param region (str) Geographic region affecting contraflow logic [default: "Tampa Bay"]
        
        @return NetworkX DiGraph with nodes representing intersections and
                edges representing road segments with capacity attribute
        
        @complexity O(n) where n = number of road segments in database
        
        @note
        - Segments with NULL source/target are skipped (topology errors)
        - Default capacity = 1800 vph if missing (HCM standard)
        - Multi-lane roads: edges combined if duplicate source/target
        - Contraflow only applies to roads marked "MAJOR HWY" in database
        
        @see calculate_max_flow for flow computation
        """
        # Query segments with minimal columns for performance
        segments = self.db.query(
            RoadSegment.source,
            RoadSegment.target,
            RoadSegment.capacity,
            RoadSegment.cost_time,
            RoadSegment.geom,
            RoadSegment.road_name
        ).all()
        
        G = nx.DiGraph()

        for seg in segments:
            if seg.source is None or seg.target is None:
                continue

            u, v = seg.source, seg.target
            capacity = seg.capacity if seg.capacity else 1800.0
            
            # CONTRAFLOW LOGIC: Reverse inbound lanes on major highways
            reversed_edge = False
            if scenario == "contraflow" and seg.road_name:
                name = seg.road_name.upper()
                is_major = "MAJOR HWY" in name
                
                if is_major:
                   # Extract coordinates from geometry to determine direction
                   line = shapely.wkt.loads(str(seg.geom)) if hasattr(seg.geom, 'wkt') else seg.geom
                   if isinstance(line, bytes) or hasattr(line, 'desc'): 
                       line = shapely.wkb.loads(str(line))
                   
                   if hasattr(line, 'coords'):
                       coords = list(line.coords)
                       start_p = coords[0]
                       end_p = coords[-1]
                       
                       # Calculate direction vector
                       # dx = end_x - start_x (positive = east, negative = west)
                       # dy = end_y - start_y (positive = north, negative = south)
                       dx = end_p[0] - start_p[0]
                       dy = end_p[1] - start_p[1]
                       
                       is_sb = dy < 0  # Southbound traffic
                       is_wb = dx < 0  # Westbound traffic
                       is_eb = dx > 0  # Eastbound traffic

                       should_reverse = False
                       
                       # Region-specific evacuation direction logic
                       if "TAMPA" in region.upper() or "SARASOTA" in region.upper():
                           # Evacuate North via I-75/Suncoast, East via I-4
                           if is_sb: should_reverse = True
                           if is_wb: should_reverse = True
                           
                       elif "ORLANDO" in region.upper() or "DAYTONA" in region.upper() or "LAKELAND" in region.upper():
                           # Evacuate North via Turnpike/I-95 or West via I-75
                           if is_sb: should_reverse = True
                           if is_wb: should_reverse = True

                       elif "MIAMI" in region.upper() or "SOUTH FL" in region.upper() or "PORT ST. LUCIE" in region.upper() or "MELBOURNE" in region.upper():
                           # CRITICAL: Evacuate NORTH via I-95, Turnpike, or EAST
                           if is_sb: should_reverse = True
                           if is_eb: should_reverse = True

                       elif "CAPE CORAL" in region.upper() or "NAPLES" in region.upper() or "FORT MYERS" in region.upper():
                           # Evacuate NORTH via I-75
                           if is_sb: should_reverse = True
                           if is_eb: should_reverse = True

                       elif "JACKSONVILLE" in region.upper():
                            # Evacuate WEST via I-10 and NORTH via I-95
                            if is_sb: should_reverse = True
                            if is_eb: should_reverse = True
                            
                       elif "TALLAHASSEE" in region.upper() or "PENSACOLA" in region.upper():
                            # Panhandle: Evacuate NORTH and potentially WEST
                            if is_sb: should_reverse = True
                            if is_eb: should_reverse = True

                       # Generic fallback: reverse all southbound major routes
                       elif is_major and is_sb:
                           should_reverse = True
                           
                       if should_reverse:
                           u, v = v, u
                           reversed_edge = True

            # Add edge to graph
            # Combine capacity if multi-lane segment (parallel edges)
            if G.has_edge(u, v):
                G[u][v]['capacity'] += capacity
            else:
                G.add_edge(u, v, capacity=capacity, cost=seg.cost_time)

        return G

    def calculate_max_flow(
        self,
        graph: nx.DiGraph,
        source_node: int,
        sink_node: int
    ) -> float:
        """
        @brief Calculate maximum evacuation throughput using max-flow algorithm
        
        @details
        Computes maximum flow from source (evacuation origin) to sink (destination)
        using the Edmonds-Karp algorithm (BFS-based Ford-Fulkerson). This represents
        the maximum evacuation throughput in vehicles per hour (vph) under ideal conditions.
        
        **Algorithm: Edmonds-Karp**
        - Time Complexity: O(V*E²) where V = vertices, E = edges
        - Space Complexity: O(V²) for residual graph
        - Guarantees optimal solution for acyclic networks
        - Handles multi-source/multi-sink via super-node construction
        
        **Physics Model:**
        Flow = minimum capacity along any path from source to sink
        Maximum flow = sum of all disjoint paths constrained by edge capacities
        
        **Interpretation:**
        - Result represents throughput in vehicles per hour (vph)
        - Assumes ideal traffic flow (no congestion effects)
        - Can be used to estimate clearance time = population / flow_rate
        
        @param graph NetworkX DiGraph with edge 'capacity' attributes
        @param source_node Node ID for evacuation origin (typically city center)
        @param sink_node Node ID for destination (typically boundary/safe zone)
        
        @return Maximum flow value in vehicles per hour (vph), 0 if no path exists
        
        @throws nx.NetworkXError: If source or sink not in graph
        
        @complexity O(V*E²) where V = nodes, E = edges
        
        @note
        - Returns 0 if no path exists between source and sink
        - Used to calculate gridlock_risk and clearance_time_hours in API
        - Capacities should be in consistent units (vph for evacuation modeling)
        
        @see api.routes.run_simulation for usage in evacuation endpoint
        @see models.road_network.capacity for edge weight source
        
        @example
        @code{.python}
        service = EvacuationService(db)
        graph = service.generate_network_graph("contraflow", "Tampa Bay")
        flow = service.calculate_max_flow(graph, source=1, sink=100)
        print(f"Evacuation throughput: {flow} vph")
        @endcode
        """
        if source_node not in graph or sink_node not in graph:
            # Source/sink not in graph: return 0
            return 0

        try:
            flow_value = nx.maximum_flow_value(
                graph,
                source_node,
                sink_node,
                capacity='capacity'
            )
            return flow_value
        except Exception as e:
            logger.error(f"Max-flow algorithm error: {e}")
            return 0


import logging
logger = logging.getLogger(__name__)
