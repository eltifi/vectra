"""
@file seed.py
@brief Database initialization and seeding on application startup

@details
Manages the database lifecycle:
- Connection health checking with exponential backoff retry logic
- Schema validation and table creation
- Automatic FDOT data download (if database empty)
- Automatic ETL pipeline invocation for data seeding
- Idempotent initialization (safe to call multiple times)

Downloads are performed in /tmp directory and deleted after seeding.
All operations are logged to logs/app.log for debugging.

@author Vectra Project
@date 2025-12-13
@version 2.0
@license AGPL-3.0

@see etl.ingest_fdot for ETL pipeline
@see db.database for engine configuration
@see models.road_network for table schema
"""

import time
import logging
import os
import shutil
import requests
import zipfile
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

## @brief Module logger for startup diagnostics
logger = logging.getLogger(__name__)

## @brief PostgreSQL connection string from environment or default
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:mysecretpassword@localhost:5432/vectra"
)

## @brief FDOT GIS Portal URL
FDOT_GIS_URL = "https://www.fdot.gov/statistics/gis/default.shtm"

## @brief Temporary directory for downloads
TMP_DATA_DIR = "/tmp/fdot_data_download"

## @brief Datasets to download - all datasets needed for Vectra
DATASETS = {
    "Basemap Routes": "basemap_route_road",
    "Interstates": "interstates",
    "Toll Roads": "toll_roads",
    "Number of Lanes": "number_of_lanes",
    "Maximum Speed Limits": "maxspeed",
    "Metropolitan Planning Organization (MPO) Area Roadways": "mpoarea",
    "Annual Average Daily Traffic": "aadt",
    "Functional Classification": "functional_classification",
    "Highway Performance Monitoring System": "hpms",
    "Federal-Aid Highway System": "federal_aid_highway",
    "Road Status": "road_status",
    "Rest Areas": "rest_areas",
}

## @brief HTTP session for requests
_session = None

def get_session():
    """Get or create HTTP session for downloads."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({'User-Agent': 'Vectra FDOT Data Download'})
    return _session


# ============================================================================
# FDOT Data Download Functions
# ============================================================================

def fetch_fdot_portal() -> str:
    """
    @brief Fetch the FDOT GIS data portal webpage
    
    @return HTML content of the portal page
    @throws requests.RequestException If unable to fetch page
    """
    logger.info(f"Fetching FDOT GIS portal: {FDOT_GIS_URL}")
    try:
        response = get_session().get(FDOT_GIS_URL, timeout=30)
        response.raise_for_status()
        logger.info(f"✓ Successfully fetched portal page ({len(response.text)} bytes)")
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Failed to fetch portal: {e}")
        raise


def parse_fdot_links(html: str) -> Dict[str, str]:
    """
    @brief Parse FDOT portal HTML to extract download links
    
    @param html HTML content of FDOT portal page
    @return Dictionary mapping dataset names to download URLs
    """
    logger.info("Parsing FDOT portal page for download links...")
    soup = BeautifulSoup(html, 'html.parser')
    links = {}
    
    for anchor in soup.find_all('a', href=True):
        href = anchor.get('href', '')
        text = anchor.get_text(strip=True)
        
        if href.endswith('.zip'):
            if href.startswith('/'):
                url = urljoin(FDOT_GIS_URL, href)
            elif href.startswith('http'):
                url = href
            else:
                continue
            
            links[text] = url
            logger.debug(f"Found: {text}")
    
    logger.info(f"✓ Found {len(links)} ZIP files on portal")
    return links


def find_dataset_links(all_links: Dict[str, str], dataset_names: Dict[str, str]) -> Dict[str, str]:
    """
    @brief Match dataset names to actual download links found on portal
    
    @param all_links All ZIP links found on portal
    @param dataset_names Required dataset names to find
    @return Dictionary mapping local directories to download URLs
    """
    logger.info("Matching datasets to portal links...")
    found_datasets = {}
    
    for portal_text, url in all_links.items():
        for dataset_name, local_dir in dataset_names.items():
            if dataset_name.lower() in portal_text.lower():
                if local_dir in found_datasets:
                    continue
                
                found_datasets[local_dir] = url
                logger.info(f"✓ Matched '{dataset_name}' → {portal_text}")
                break
    
    missing = set(dataset_names.values()) - set(found_datasets.keys())
    if missing:
        logger.warning(f"⚠ Could not find {len(missing)} datasets: {missing}")
    
    return found_datasets


def download_file(url: str, destination: Path, retries: int = 3) -> bool:
    """
    @brief Download a file from URL with retry logic
    
    @param url Primary URL to download from
    @param destination Path where file should be saved
    @param retries Number of retry attempts
    @return True if successful, False otherwise
    """
    for attempt in range(retries):
        try:
            logger.info(f"Downloading {url}")
            response = get_session().get(url, timeout=60, stream=True, allow_redirects=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(destination, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            logger.info(f"✓ Downloaded {downloaded:,} bytes")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"✗ Download attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                logger.info("Retrying in 5 seconds...")
                time.sleep(5)
            continue
    
    logger.error(f"✗ Failed to download after {retries} attempts")
    return False


def extract_zip(zip_path: Path, target_dir: Path) -> bool:
    """
    @brief Extract ZIP file to target directory
    
    @param zip_path Path to ZIP file
    @param target_dir Directory to extract into
    @return True if successful, False otherwise
    """
    try:
        logger.info(f"Extracting to {target_dir}")
        os.makedirs(target_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
        
        logger.info(f"✓ Extracted successfully")
        return True
        
    except zipfile.BadZipFile:
        logger.error(f"✗ Invalid ZIP file: {zip_path}")
        return False
    except Exception as e:
        logger.error(f"✗ Extraction error: {e}")
        return False


def validate_shapefile(target_dir: Path) -> bool:
    """
    @brief Validate that shapefile was extracted correctly
    
    @param target_dir Directory containing extracted files
    @return True if required shapefile components present, False otherwise
    """
    required_extensions = ['.shp', '.shx', '.dbf']
    found_extensions = set()
    
    for file_path in target_dir.glob('*'):
        if file_path.suffix.lower() in required_extensions:
            found_extensions.add(file_path.suffix.lower())
    
    if found_extensions == set(required_extensions):
        logger.info(f"✓ Shapefile validated (found .shp, .shx, .dbf)")
        return True
    else:
        missing = set(required_extensions) - found_extensions
        logger.warning(f"⚠ Missing shapefile components: {missing}")
        return False


def download_dataset(dataset_name: str, dataset_url: str, target_dir: Path) -> bool:
    """
    @brief Download and extract a single FDOT dataset
    
    @param dataset_name Name of dataset
    @param dataset_url Download URL
    @param target_dir Directory to extract into
    @return True if successful, False otherwise
    """
    logger.info(f"\nDownloading: {dataset_name}")
    
    # Download ZIP
    zip_path = target_dir.parent / f"{dataset_name}.zip"
    
    if not download_file(dataset_url, zip_path):
        logger.error(f"✗ Failed to download {dataset_name}")
        return False
    
    # Verify ZIP is valid
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if zf.testzip() is not None:
                logger.warning(f"⚠ ZIP file may be corrupted")
    except zipfile.BadZipFile:
        logger.error(f"✗ Downloaded file is not a valid ZIP")
        zip_path.unlink(missing_ok=True)
        return False
    
    # Extract ZIP
    if not extract_zip(zip_path, target_dir):
        zip_path.unlink(missing_ok=True)
        return False
    
    # Validate
    if not validate_shapefile(target_dir):
        logger.warning(f"⚠ Validation incomplete - may still be usable")
    
    # Cleanup ZIP
    try:
        zip_path.unlink()
        logger.info(f"✓ Cleaned up ZIP file")
    except Exception as e:
        logger.warning(f"⚠ Could not delete ZIP: {e}")
    
    return True


def download_fdot_data() -> bool:
    """
    @brief Download all FDOT datasets to temporary directory
    
    @details
    Downloads all required FDOT datasets to /tmp/fdot_data_download.
    This is only called if database is empty (first run).
    
    @return True if all datasets downloaded successfully, False otherwise
    """
    logger.info("\n" + "="*70)
    logger.info("FDOT GIS Data Download (Database is Empty)")
    logger.info("="*70)
    logger.info(f"FDOT GIS Portal: {FDOT_GIS_URL}")
    logger.info(f"Download directory: {TMP_DATA_DIR}\n")
    
    # Create temp directory
    try:
        os.makedirs(TMP_DATA_DIR, exist_ok=True)
        logger.info(f"✓ Created temporary download directory")
    except Exception as e:
        logger.error(f"✗ Failed to create temp directory: {e}")
        return False
    
    try:
        # Fetch and parse FDOT portal
        logger.info("Connecting to FDOT GIS portal...")
        html = fetch_fdot_portal()
        all_links = parse_fdot_links(html)
        
        # Find datasets
        logger.info(f"\nLooking for {len(DATASETS)} datasets...")
        dataset_links = find_dataset_links(all_links, DATASETS)
        
        if not dataset_links:
            logger.error("✗ Could not find any datasets on FDOT portal")
            logger.error(f"Please check: {FDOT_GIS_URL}")
            return False
        
        # Download all datasets
        logger.info(f"\nDownloading {len(dataset_links)} datasets...")
        failed_datasets = []
        
        for local_dir, url in dataset_links.items():
            target_dir = Path(TMP_DATA_DIR) / local_dir
            if not download_dataset(local_dir, url, target_dir):
                failed_datasets.append(local_dir)
        
        # Summary
        successful = len(dataset_links) - len(failed_datasets)
        logger.info(f"\n{'='*70}")
        logger.info(f"Download Summary: {successful}/{len(dataset_links)} successful")
        
        if failed_datasets:
            logger.warning(f"Failed datasets: {failed_datasets}")
            return False
        
        logger.info("✓ All datasets downloaded successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Download error: {e}", exc_info=True)
        return False


def wait_for_database(max_retries: int = 30, retry_delay: int = 2) -> bool:
    """
    @brief Wait for database to become available with exponential retry
    
    @details
    Implements connection health checking with configurable retry parameters.
    Useful for containerized deployments where database may start after app.
    
    **Algorithm:**
    1. Attempt connection via test query: `SELECT 1`
    2. On failure: exponential backoff with configurable delay
    3. On success: log and return immediately
    4. On max_retries exceeded: log error and return False
    
    @param max_retries (int) Maximum connection attempts [default: 30]
    @param retry_delay (int) Delay between retries in seconds [default: 2]
    
    @return True if database available, False if max retries exceeded
    
    @note
    - Typically takes 10-60 seconds for database to become available
    - Production: increase max_retries for slow database startup
    - Useful for docker-compose initialization
    
    @complexity O(max_retries) attempts, O(max_retries * retry_delay) wall time
    
    @see initialize_database for usage in app startup
    """
    retries = 0
    while retries < max_retries:
        try:
            engine = create_engine(DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✓ Database connection established successfully")
            return True
        except OperationalError as e:
            retries += 1
            logger.warning(
                f"Database not ready (attempt {retries}/{max_retries}): {str(e)[:100]}"
            )
            if retries < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
    
    logger.error(f"Failed to connect to database after {max_retries} attempts")
    return False


def check_database_seeded(engine) -> bool:
    """
    @brief Verify database has been seeded with FDOT road network data
    
    @details
    Checks:
    1. If road_segments table exists
    2. If table contains data (non-zero row count)
    3. If all required columns are present (rd_status, is_interstate, is_toll_road)
    
    Supports schema evolution: detects when new columns added requiring re-seeding.
    
    @param engine SQLAlchemy Engine instance
    
    @return True if database fully seeded, False if needs initialization
    
    @note
    - Safe to call multiple times (idempotent)
    - Returns False for any schema validation failure
    - Logs detailed information about missing columns
    
    @see seed_database for seeding workflow
    """
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if "road_segments" not in tables:
            logger.info("road_segments table not found - database needs seeding")
            return False
        
        with engine.begin() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM road_segments"))
            count = result.scalar()
            
            if count == 0:
                logger.info("road_segments table is empty - database needs seeding")
                return False
            
            # Verify schema columns exist (required by business logic)
            columns = inspector.get_columns("road_segments")
            column_names = [col['name'] for col in columns]
            
            required_columns = ["rd_status", "is_interstate", "is_toll_road"]
            missing_columns = [col for col in required_columns if col not in column_names]
            
            if missing_columns:
                logger.info(
                    f"Missing columns {missing_columns} - "
                    "database schema needs updating (re-seeding required)"
                )
                return False
            
            logger.info(f"✓ Database already seeded with {count} road segments")
            return True
    except Exception as e:
        logger.warning(f"Error checking database seed status: {e}")
        return False


def seed_database_from_tmp() -> bool:
    """
    @brief Execute ETL pipeline using data from /tmp, then cleanup
    
    @details
    1. Temporarily sets RAW_DATA_PATH to /tmp/fdot_data_download
    2. Runs ETL pipeline to load datasets one by one
    3. Deletes temporary directory after seeding
    4. Restores original RAW_DATA_PATH
    
    @return True if seeding successful, False on error
    """
    from app.etl.ingest_fdot import run_etl
    
    original_raw_path = os.getenv("RAW_DATA_PATH", "/app/data")
    
    try:
        # Temporarily set data path to /tmp
        os.environ["RAW_DATA_PATH"] = TMP_DATA_DIR
        logger.info(f"Seeding from temporary directory: {TMP_DATA_DIR}")
        
        # Run ETL pipeline
        logger.info("Starting ETL pipeline to load datasets...")
        run_etl()
        logger.info("✓ Database seeding completed successfully")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during database seeding: {e}", exc_info=True)
        return False
    
    finally:
        # Cleanup temporary directory
        try:
            if os.path.exists(TMP_DATA_DIR):
                logger.info(f"Cleaning up temporary directory: {TMP_DATA_DIR}")
                shutil.rmtree(TMP_DATA_DIR)
                logger.info("✓ Temporary directory cleaned up")
        except Exception as e:
            logger.warning(f"⚠ Could not clean up temp directory: {e}")
        
        # Restore original path
        os.environ["RAW_DATA_PATH"] = original_raw_path


def seed_database() -> bool:
    """
    @brief Execute ETL pipeline to populate database with FDOT data
    
    @details
    Invokes the ETL (Extract-Transform-Load) pipeline to:
    1. Load FDOT official shapefiles (interstates, toll roads, etc.)
    2. Transform and validate geometry and attributes
    3. Load data into PostGIS database
    4. Build spatial indexes and network topology
    
    Process is idempotent: skipped if already seeded (by check_database_seeded).
    
    **ETL Stages:**
    1. EXTRACT: Load from shapefiles in backend/data/
    2. TRANSFORM: Reproject, clean, calculate attributes
    3. LOAD: Insert into PostgreSQL/PostGIS
    4. POST-PROCESS: Build pgRouting topology, add indexes
    
    @return True if seeding successful, False on error
    
    @note
    - First run: 30-60 seconds depending on I/O
    - Idempotent: safe to call multiple times (only seeds once)
    - Requires FDOT shapefiles in backend/data/ directory
    
    @throws None (errors logged and returned as bool)
    
    @see etl.ingest_fdot for detailed implementation
    @see check_database_seeded for skip logic
    """
    from app.etl.ingest_fdot import run_etl
    
    try:
        engine = create_engine(DATABASE_URL)
        
        # Check if already seeded - skip if so
        if check_database_seeded(engine):
            logger.info("Skipping database seeding - already seeded")
            return True
        
        logger.info("Starting database seeding with FDOT data...")
        run_etl()
        logger.info("✓ Database seeding completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error during database seeding: {e}", exc_info=True)
        return False


def seed_mpos(engine) -> bool:
    """
    @brief Seed the metropolitan_areas table with MPO data from FDOT shapefile
    
    @details
    Loads unique Metropolitan Planning Organization (MPO) areas from the
    FDOT MPO Area Roadways shapefile and inserts them into the database.
    This is idempotent - existing MPOs are skipped.
    
    @param engine SQLAlchemy Engine instance
    
    @return True if seeding successful, False on error
    
    @note
    - Data source: FDOT MPO Area Roadways shapefile (data/raw/mpoarea/mpoarea.shp)
    - Excludes MPO code '00' (None/no MPO areas)
    - On first run: loads all unique MPOs from shapefile
    - On subsequent runs: skips if table already seeded (idempotent)
    
    @see app.models.msa for MetropolitanArea data model
    """
    try:
        import geopandas as gpd
        
        raw_data_path = os.getenv("RAW_DATA_PATH", "/app/data")
        mpo_shp_path = os.path.join(raw_data_path, "mpoarea", "mpoarea.shp")
        
        if not os.path.exists(mpo_shp_path):
            logger.warning(f"MPO shapefile not found at {mpo_shp_path}")
            return False
        
        logger.info(f"Loading MPO data from {mpo_shp_path}")
        mpo_gdf = gpd.read_file(mpo_shp_path)
        
        # Extract unique MPO areas (excluding None/00 codes)
        mpo_data = mpo_gdf[['MPONAME', 'MPOCD']].drop_duplicates()
        mpo_data = mpo_data[mpo_data['MPOCD'] != '00']  # Exclude "None" code
        mpo_data = mpo_data[mpo_data['MPONAME'].notna()]  # Exclude null names
        
        logger.info(f"Found {len(mpo_data)} unique MPO areas")
        
        # Insert into database
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        
        try:
            # Check if already seeded
            existing_count = db.execute(text("SELECT COUNT(*) FROM metropolitan_areas")).scalar()
            
            if existing_count > 0:
                logger.info(f"MSA table already seeded with {existing_count} areas - skipping")
                db.close()
                return True
            
            # Insert each MPO
            for _, row in mpo_data.iterrows():
                insert_query = text("""
                    INSERT INTO metropolitan_areas (name, mpo_code, state)
                    VALUES (:name, :mpo_code, :state)
                    ON CONFLICT (mpo_code) DO NOTHING
                """)
                db.execute(insert_query, {
                    "name": str(row['MPONAME']).strip(),
                    "mpo_code": str(row['MPOCD']).strip(),
                    "state": "FL"
                })
            
            db.commit()
            logger.info(f"✓ Seeded {len(mpo_data)} MPO areas from shapefile")
            db.close()
            return True
            
        except Exception as e:
            db.close()
            logger.error(f"Error inserting MSAs: {e}", exc_info=True)
            return False
            
    except ImportError:
        logger.error("GeoPandas not available - cannot seed MSAs from shapefile")
        return False
    except Exception as e:
        logger.error(f"Error seeding MSAs from shapefile: {e}", exc_info=True)
        return False


def seed_rest_areas(engine) -> bool:
    """
    @brief Seed the rest_areas table with FDOT rest area locations
    
    @details
    Loads rest areas and welcome centers from the FDOT Rest Areas shapefile.
    These locations serve as potential staging and evacuation assembly points.
    
    @param engine SQLAlchemy Engine instance
    
    @return True if seeding successful, False on error
    
    @note
    - Data source: FDOT Rest Areas/Welcome Centers shapefile
    - On first run: loads all rest areas from shapefile
    - On subsequent runs: skips if table already seeded (idempotent)
    """
    try:
        import geopandas as gpd
        from geoalchemy2 import WKTElement
        
        raw_data_path = os.getenv("RAW_DATA_PATH", "/app/data")
        rest_areas_shp_path = os.path.join(raw_data_path, "rest_areas", "rest_areas.shp")
        
        db = sessionmaker(bind=engine)()
        
        try:
            # Check if already seeded
            existing_count = db.execute(text("SELECT COUNT(*) FROM rest_areas")).scalar()
            
            if existing_count > 0:
                logger.info(f"Rest areas table already seeded with {existing_count} locations - skipping")
                db.close()
                return True
            
            # Load rest areas shapefile
            if not os.path.exists(rest_areas_shp_path):
                logger.warning(f"Rest areas shapefile not found: {rest_areas_shp_path}")
                db.close()
                return True
            
            rest_areas_gdf = gpd.read_file(rest_areas_shp_path)
            logger.info(f"Loaded {len(rest_areas_gdf)} rest areas from shapefile")
            
            # Insert each rest area
            for _, row in rest_areas_gdf.iterrows():
                insert_query = text("""
                    INSERT INTO rest_areas (geom, name, facility_type, interstate, direction, state)
                    VALUES (ST_GeomFromText(:geom, 4326), :name, :facility_type, :interstate, :direction, :state)
                    ON CONFLICT DO NOTHING
                """)
                
                geom_wkt = row.geometry.wkt
                
                db.execute(insert_query, {
                    "geom": geom_wkt,
                    "name": str(row.get('NAME', '')).strip() if 'NAME' in row else None,
                    "facility_type": str(row.get('FACILITY_TYPE', '')).strip() if 'FACILITY_TYPE' in row else None,
                    "interstate": str(row.get('INTERSTATE', '')).strip() if 'INTERSTATE' in row else None,
                    "direction": str(row.get('DIRECTION', '')).strip() if 'DIRECTION' in row else None,
                    "state": "FL"
                })
            
            db.commit()
            logger.info(f"✓ Seeded {len(rest_areas_gdf)} rest areas from shapefile")
            db.close()
            return True
            
        except Exception as e:
            db.close()
            logger.error(f"Error inserting rest areas: {e}", exc_info=True)
            return False
            
    except ImportError:
        logger.warning("GeoPandas not available - cannot seed rest areas from shapefile")
        return False
    except Exception as e:
        logger.error(f"Error seeding rest areas: {e}", exc_info=True)
        return False


def initialize_database() -> bool:
    """
    @brief Main entry point for database initialization on app startup
    
    @details
    Orchestrates complete database initialization workflow:
    1. Wait for PostgreSQL to be available (handles containerized deployments)
    2. Create table schema (idempotent via SQLAlchemy metadata)
    3. Download FDOT data if database is empty (from FDOT portal)
    4. Seed database with FDOT data if needed
    
    **Failure Handling:**
    - Logs all errors with full stack traces
    - Gracefully degrades: app continues even if seeding fails
    - Allows developers to run app without full data for testing
    
    @return True if all steps successful, False if any step fails
    
    @note
    - Called automatically on FastAPI startup
    - Total execution time: 10-5 minutes depending on I/O and network
    - Safe to call multiple times (idempotent workflow)
    - Designed for Docker container startup
    - Downloads to /tmp and deletes after seeding
    
    @throws None (all errors logged and returned as bool)
    
    @see main.py for initialization call
    @see api.routes for failure impact (may return empty data)
    
    @complexity O(n) where n = number of road segments (first run only)
    """
    logger.info("Starting database initialization...")
    
    # Step 1: Wait for database to be available
    if not wait_for_database(max_retries=1, retry_delay=1):
        logger.error("Could not establish database connection - proceeding anyway")
        return False
    
    # Step 2: Create tables
    try:
        from app.db.base import Base
        from app.db.database import engine as main_engine
        
        logger.info("Creating tables...")
        Base.metadata.create_all(bind=main_engine)
        logger.info("✓ Tables created/verified")
    except Exception as e:
        logger.error(f"Error creating tables: {e}", exc_info=True)
        return False
    
    # Step 3: Check if database is empty and needs data
    try:
        engine = create_engine(DATABASE_URL)
        if not check_database_seeded(engine):
            logger.info("\n✓ Database is empty - downloading FDOT data...")
            if not download_fdot_data():
                logger.error("✗ Failed to download FDOT data")
                return False
    except Exception as e:
        logger.warning(f"⚠ Could not check database seed status: {e}")
    
    # Step 4: Seed database if needed
    if not seed_database_from_tmp():
        logger.error("Database seeding failed - application may not work correctly")
        return False
    
    # Step 5: Seed MSAs from MPO shapefile
    try:
        logger.info("Seeding MSA data from MPO shapefile...")
        if not seed_mpos(main_engine):
            logger.error("MSA seeding failed")
            return False
    except Exception as e:
        logger.error(f"Error seeding MSAs: {e}", exc_info=True)
        return False
    
    # Step 6: Seed rest areas from shapefile
    try:
        logger.info("Seeding rest areas from FDOT shapefile...")
        if not seed_rest_areas(main_engine):
            logger.warning("Rest areas seeding failed - continuing")
    except Exception as e:
        logger.warning(f"Error seeding rest areas: {e}", exc_info=True)
    
    logger.info("✓ Database initialization completed successfully")
    return True
