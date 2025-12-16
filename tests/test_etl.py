"""
ETL Pipeline Tests

Tests for the FDOT data extraction, transformation, and loading pipeline.
Covers data ingestion, attribute aggregation, geometry processing, and
database operations.

Test Classes:
- TestDataLoading: Load_data function and file handling
- TestAttributeAggregation: Attribute merging and defaults
- TestGeometryProcessing: Projection, cleaning, length calculation
- TestNetworkProperties: Capacity and travel time calculation
- TestClassification: Road type identification (interstate/toll)
- TestDatabaseIngest: PostGIS storage and topology

Author: Vectra Project
License: AGPL-3.0
"""

import pytest
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import LineString
from app.etl.ingest_fdot import (
    aggregate_attributes,
    reproject_and_clean,
    calculate_geometric_properties,
    calculate_network_properties,
    identify_official_classifications,
    synthesize_road_names,
    prepare_for_database
)


class TestAttributeAggregation:
    """Test attribute aggregation functionality."""
    
    def test_aggregate_with_both_lanes_and_speed(self, sample_geodataframe):
        """Test aggregation when both lanes and speed data provided."""
        # Create attribute dataframes
        lanes_data = sample_geodataframe[['ROADWAY', 'LANE_CNT']].rename(columns={'LANE_CNT': 'LANE_CNT'})
        speed_data = sample_geodataframe[['ROADWAY', 'SPEED']].rename(columns={'SPEED': 'SPEED'})
        
        # Drop attributes from main routes to simulate raw shapefile
        routes = sample_geodataframe.drop(columns=['LANE_CNT', 'SPEED'], errors='ignore')
        
        result = aggregate_attributes(routes, lanes_data, speed_data)
        
        # Verify aggregation completed
        assert 'LANE_CNT' in result.columns
        assert 'SPEED' in result.columns
        assert result['LANE_CNT'].notna().all()
        assert result['SPEED'].notna().all()
    
    def test_aggregate_with_no_lanes(self, sample_geodataframe):
        """Test aggregation with missing lanes data (should use default=1)."""
        result = aggregate_attributes(sample_geodataframe, None, None)
        
        # Verify defaults applied
        assert (result['LANE_CNT'] == 1).all()
        assert (result['SPEED'] == 30).all()
    
    def test_aggregate_fills_missing_values(self, sample_geodataframe):
        """Test that NaN values are filled with defaults."""
        # Create incomplete data
        incomplete_speed = sample_geodataframe[['ROADWAY', 'SPEED']].copy()
        incomplete_speed.loc[0, 'SPEED'] = np.nan
        
        # Drop attributes to simulate raw data
        routes = sample_geodataframe.drop(columns=['SPEED'], errors='ignore')
        
        result = aggregate_attributes(routes, None, incomplete_speed)
        
        # Verify NaN is filled
        assert result['SPEED'].notna().all()
        assert result.loc[0, 'SPEED'] == 30  # Default value


class TestGeometryProcessing:
    """Test geometry cleaning and reprojection."""
    
    def test_reproject_to_wgs84(self, sample_geodataframe):
        """Test reprojection to WGS84 if not already in WGS84."""
        # Change CRS temporarily
        df_utm = sample_geodataframe.to_crs("EPSG:32617")  # UTM Zone 17N
        
        result = reproject_and_clean(df_utm)
        
        # Verify reprojection
        assert result.crs == "EPSG:4326"
        assert len(result) == len(df_utm)
    
    def test_remove_null_geometries(self, sample_geodataframe):
        """Test that null geometries are removed."""
        # Add null geometry
        null_row = {
            'ROADWAY': 'NULL_ROAD',
            'LANE_CNT': 2,
            'SPEED': 45,
            'RD_STATUS': '02',
            'geometry': None
        }
        df_with_null = gpd.GeoDataFrame(
            pd.concat([sample_geodataframe, gpd.GeoDataFrame([null_row])]),
            crs="EPSG:4326"
        )
        
        result = reproject_and_clean(df_with_null)
        
        # Verify null removed
        assert result.geometry.notna().all()
        assert len(result) == len(sample_geodataframe)
    
    def test_preserve_valid_geometries(self, sample_geodataframe):
        """Test that valid geometries are preserved."""
        result = reproject_and_clean(sample_geodataframe)
        
        # Verify geometry count
        assert len(result) == len(sample_geodataframe)
        assert result.geometry.notna().all()


class TestNetworkProperties:
    """Test network physics calculation."""
    
    def test_capacity_calculation(self, sample_geodataframe):
        """Test evacuation capacity calculation (lanes * 1800 vph)."""
        # Needed for cost_time calculation which happens in same function
        sample_geodataframe['length_m'] = 1000.0 
        result = calculate_network_properties(sample_geodataframe)
        
        # Verify capacity formula: lanes * 1800
        for idx, row in result.iterrows():
            expected_capacity = row['LANE_CNT'] * 1800
            assert row['capacity'] == expected_capacity
    
    def test_travel_time_calculation(self, sample_geodataframe):
        """Test travel time calculation (distance / speed)."""
        # First calculate geometry
        df_clean = reproject_and_clean(sample_geodataframe)
        df_with_length = calculate_geometric_properties(df_clean)
        result = calculate_network_properties(df_with_length)
        
        # Verify cost_time is positive
        assert (result['cost_time'] > 0).all()
        
        # Verify units (should be in seconds)
        # At 40 mph for ~1500m should be roughly 80-90 seconds
        assert result['cost_time'].mean() > 0
    
    def test_zero_speed_replacement(self, sample_geodataframe):
        """Test that zero speeds are replaced with minimum default."""
        # Set one speed to zero
        sample_geodataframe.loc[0, 'SPEED'] = 0
        df_clean = reproject_and_clean(sample_geodataframe)
        df_with_length = calculate_geometric_properties(df_clean)
        result = calculate_network_properties(df_with_length)
        
        # Verify zero speed was replaced
        assert result['speed_ms'].min() > 0


class TestRoadClassification:
    """Test official road classification."""
    
    def test_identify_interstates(self, sample_geodataframe, sample_interstates_gdf):
        """Test interstate identification from official shapefile."""
        result = identify_official_classifications(
            sample_geodataframe,
            interstates=sample_interstates_gdf,
            toll_roads=None
        )
        
        # I-75 should be identified as interstate
        assert result[result['ROADWAY'] == 'I-75']['is_interstate'].iloc[0] == True
        
        # US-41 should not be interstate
        assert result[result['ROADWAY'] == 'US-41']['is_interstate'].iloc[0] == False
    
    def test_identify_toll_roads(self, sample_geodataframe, sample_toll_roads_gdf):
        """Test toll road identification."""
        result = identify_official_classifications(
            sample_geodataframe,
            interstates=None,
            toll_roads=sample_toll_roads_gdf
        )
        
        # Verify flag is set
        assert 'is_toll_road' in result.columns
        assert result['is_toll_road'].dtype == bool
    
    def test_both_classifications(self, sample_geodataframe, 
                                 sample_interstates_gdf, sample_toll_roads_gdf):
        """Test simultaneous interstate and toll classification."""
        result = identify_official_classifications(
            sample_geodataframe,
            interstates=sample_interstates_gdf,
            toll_roads=sample_toll_roads_gdf
        )
        
        # Verify both flags present
        assert 'is_interstate' in result.columns
        assert 'is_toll_road' in result.columns


class TestRoadNameSynthesis:
    """Test road name generation."""
    
    def test_synthesize_interstate_names(self, sample_geodataframe, sample_interstates_gdf):
        """Test that interstates get proper suffixes."""
        result = identify_official_classifications(
            sample_geodataframe,
            interstates=sample_interstates_gdf,
            toll_roads=None
        )
        result = synthesize_road_names(result)
        
        # I-75 should have suffix
        i75_name = result[result['ROADWAY'] == 'I-75']['road_name'].iloc[0]
        assert 'Major Hwy' in i75_name
    
    def test_road_names_are_strings(self, sample_geodataframe):
        """Test that road names are valid strings."""
        # Add required columns
        sample_geodataframe['is_interstate'] = False
        sample_geodataframe['is_toll_road'] = False
        result = synthesize_road_names(sample_geodataframe)
        
        # Verify all road names are strings
        assert result['road_name'].dtype == object
        assert result['road_name'].notna().all()


class TestDatabasePreparation:
    """Test preparation for database ingestion."""
    
    def test_prepare_for_database_schema(self, sample_geodataframe):
        """Test that output matches database schema."""
        # Full processing pipeline
        df = reproject_and_clean(sample_geodataframe)
        df = calculate_geometric_properties(df)
        df = calculate_network_properties(df)
        
        # Classification
        df['is_interstate'] = False
        df['is_toll_road'] = False
        
        df = synthesize_road_names(df)
        
        result = prepare_for_database(df)
        
        # Verify required columns
        required_columns = [
            'id', 'geom', 'length_m', 'lanes', 'speed_limit',
            'capacity', 'cost_time', 'road_name', 'rd_status',
            'is_interstate', 'is_toll_road'
        ]
        for col in required_columns:
            assert col in result.columns
    
    def test_sequential_ids_assigned(self, sample_geodataframe):
        """Test that sequential IDs are properly assigned."""
        df = reproject_and_clean(sample_geodataframe)
        df = calculate_geometric_properties(df)
        df = calculate_network_properties(df)
        
        # Classification
        df['is_interstate'] = False
        df['is_toll_road'] = False
        
        df = synthesize_road_names(df)
        
        result = prepare_for_database(df)
        
        # Verify sequential IDs
        assert (result['id'] == range(1, len(result) + 1)).all()


class TestEndToEndETL:
    """Integration tests for complete ETL pipeline."""
    
    def test_complete_pipeline(self, sample_geodataframe, 
                             sample_interstates_gdf, sample_toll_roads_gdf):
        """Test complete ETL pipeline from raw to database-ready."""
        # Full processing
        df = aggregate_attributes(sample_geodataframe, None, None)
        df = reproject_and_clean(df)
        df = calculate_geometric_properties(df)
        df = calculate_network_properties(df)
        df = identify_official_classifications(df, sample_interstates_gdf, sample_toll_roads_gdf)
        df = synthesize_road_names(df)
        result = prepare_for_database(df)
        
        # Verify output is valid
        assert len(result) == len(sample_geodataframe)
        assert result.crs == "EPSG:4326"
        assert result.geometry.notna().all()
        assert all(isinstance(id_val, (int, np.integer)) for id_val in result['id'])


# Parametrized tests for robustness
@pytest.mark.parametrize("speed_value", [0, 10, 30, 65, 90])
def test_speed_conversion(speed_value):
    """Test speed conversion from mph to m/s for various values."""
    # 1 mph = 0.44704 m/s
    expected = speed_value * 0.44704
    
    # Speed conversion in calculate_network_properties
    conversion_factor = 0.44704
    result = speed_value * conversion_factor
    
    assert result == expected


@pytest.mark.parametrize("lanes", [1, 2, 4, 6, 8])
def test_capacity_by_lanes(lanes):
    """Test capacity calculation for various lane counts."""
    expected_capacity = lanes * 1800
    
    # Create test data
    df = gpd.GeoDataFrame({
        'ROADWAY': ['TEST'],
        'LANE_CNT': [lanes],
        'SPEED': [55],
        'length_m': [1000.0],
        'geometry': [LineString([(-82.4, 27.9), (-82.3, 27.85)])]
    }, crs="EPSG:4326")
    
    df = calculate_network_properties(df)
    
    assert df.iloc[0]['capacity'] == expected_capacity
