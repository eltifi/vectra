# Vectra API Documentation

Base URL: `http://localhost:8000` (Local) / `https://api.vectra.io` (Production)

## Core Endpoints

### 1. Road Network Segments
Retrieve the complete road network geometry and metadata as a GeoJSON FeatureCollection.

- **Endpoint**: `/segments`
- **Method**: `GET`
- **Description**: Returns all road segments merged by road name. Used for rendering the map visualization.
- **Response**: GeoJSON `FeatureCollection`
  ```json
  {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": {
          "type": "MultiLineString",
          "coordinates": [...]
        },
        "properties": {
          "id": 101,
          "name": "I-75",
          "lanes": 3,
          "speed_limit": 70,
          "road_type": "interstate" // interstate, toll, major, standard
        }
      }
    ]
  }
  ```

### 2. Evacuation Simulation
Run a max-flow evacuation simulation for a specific disaster scenario.

- **Endpoint**: `/simulate`
- **Method**: `GET`
- **Parameters**:
  - `scenario` (optional): The ID of the disaster scenario (e.g., `baseline`, `cat5_direct_hit`). Default: `baseline`.
  - `region` (optional): The target geographic region. Default: `Tampa Bay`.
- **Response**: Simulation Results JSON
  ```json
  {
    "scenario": "baseline",
    "max_throughput_vph": 12500,
    "clearance_time_hours": 28.5,
    "gridlock_risk": "CRITICAL", // LOW, MODERATE, CRITICAL
    "graph_size": {
      "nodes": 4500,
      "edges": 5200
    },
    "description": "Real-time calculation using Edmonds-Karp..."
  }
  ```

### 3. Scenarios List
Retrieve configuration for all available disaster scenarios.

- **Endpoint**: `/scenarios`
- **Method**: `GET`
- **Description**: Returns a list of scientific disaster definitions used to populate the simulation selection UI.
- **Response**: JSON Array
  ```json
  {
    "scenarios": [
      {
        "id": "nw_gulf_approach",
        "label": "NW - Gulf Approach (Tampa Bay)",
        "category": 4,
        "windSpeed": 145,
        "affectedRegions": ["Pinellas", "Hillsborough"]
      }
    ]
  }
  ```

### 4. Metropolitan Areas (MSAs)
Retrieve Florida Metropolitan Planning Organization (MPO) boundaries.

- **Endpoint**: `/msas`
- **Method**: `GET`
- **Description**: Returns MPO regions for map overlays and regional selection.
- **Response**: GeoJSON `FeatureCollection` (Points/Polygons) or List
  ```json
  {
      "type": "FeatureCollection",
      "features": [
          {
              "id": 1,
              "name": "Tampa Bay Area",
              "mpo_code": "T1",
              "state": "FL"
          }
      ],
      "count": 12
  }
  ```

## System & Health

### Health Checkers
Verify system status and readiness.

- **General Health**: `GET /health`
  - Returns `200 OK` if healthy.
  - Returns `503 Service Unavailable` if in maintenance mode or DB is down.
  ```json
  {
    "status": "healthy",
    "components": {
      "database": "connected",
      "cache": "connected"
    }
  }
  ```

- **Readiness Probe**: `GET /health/ready` (Returns 200/503)
- **Liveness Probe**: `GET /health/live` (Returns 200 always)
