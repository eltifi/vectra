#!/usr/bin/env bash
set -e

# Test Runner for Docker Container
# 
# This script runs tests inside the Docker container.
# It can be called from outside the container.
#
# Usage:
#   ./scripts/run_tests.sh              # Run all tests
#   ./scripts/run_tests.sh unit         # Run only unit tests
#   ./scripts/run_tests.sh quick        # Skip slow/integration tests
#   ./scripts/run_tests.sh coverage     # Generate coverage report
#
# Environment Variables:
#   CONTAINER_NAME: Name of running container (default: vectra-backend)
#   IMAGE_NAME: Docker image name (default: vectra:latest)
#
# Author: Vectra Project
# License: AGPL-3.0

CONTAINER_NAME="${CONTAINER_NAME:-vectra-backend}"
IMAGE_NAME="${IMAGE_NAME:-vectra:latest}"
TEST_DIR="/app/tests"
LOGS_DIR="/app/tests"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Vectra Test Suite Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}ℹ Container '${CONTAINER_NAME}' is not running${NC}"
    echo -e "${YELLOW}ℹ Starting container...${NC}"
    docker run -d \
        --name "${CONTAINER_NAME}" \
        -e LOG_OUTPUT=stdout \
        -p 8000:8000 \
        "${IMAGE_NAME}" \
        2>/dev/null || {
            echo -e "${RED}✗ Failed to start container${NC}"
            exit 1
        }
    
    # Wait for container to be ready
    echo "Waiting for container to be ready..."
    sleep 5
fi

echo -e "${BLUE}Running tests in container: ${CONTAINER_NAME}${NC}\n"

# Build pytest command
PYTEST_CMD="python -m pytest /app/tests -v --tb=short"
PYTEST_CMD="${PYTEST_CMD} --cov=app --cov-report=term-missing"
PYTEST_CMD="${PYTEST_CMD} --cov-report=html:${TEST_DIR}/coverage_html"
PYTEST_CMD="${PYTEST_CMD} --cov-report=json:${TEST_DIR}/coverage.json"
PYTEST_CMD="${PYTEST_CMD} --cov-report=xml:${TEST_DIR}/coverage.xml"
PYTEST_CMD="${PYTEST_CMD} --junitxml=${TEST_DIR}/junit.xml"
PYTEST_CMD="${PYTEST_CMD} --log-cli=true --log-cli-level=INFO"
PYTEST_CMD="${PYTEST_CMD} --log-file=${LOGS_DIR}/test_results.log"
PYTEST_CMD="${PYTEST_CMD} --log-file-level=DEBUG"

# Handle test options
if [[ "$1" == "unit" ]]; then
    echo -e "${BLUE}Mode: Unit Tests Only${NC}"
    PYTEST_CMD="${PYTEST_CMD} -m unit"
elif [[ "$1" == "quick" ]]; then
    echo -e "${BLUE}Mode: Quick Tests (skipping slow/integration)${NC}"
    PYTEST_CMD="${PYTEST_CMD} -m 'not slow and not integration'"
elif [[ "$1" == "coverage" ]]; then
    echo -e "${BLUE}Mode: Full Coverage Report${NC}"
    PYTEST_CMD="${PYTEST_CMD} --cov-report=html:${TEST_DIR}/coverage_html"
fi

echo ""

# Run tests in container
docker exec "${CONTAINER_NAME}" bash -c "${PYTEST_CMD}"
RESULT=$?

# Copy test results from container
echo ""
echo -e "${BLUE}Copying test results...${NC}"

mkdir -p tests/coverage_html
docker cp "${CONTAINER_NAME}:${TEST_DIR}/coverage.json" tests/ 2>/dev/null || true
docker cp "${CONTAINER_NAME}:${TEST_DIR}/coverage.xml" tests/ 2>/dev/null || true
docker cp "${CONTAINER_NAME}:${TEST_DIR}/junit.xml" tests/ 2>/dev/null || true
docker cp "${CONTAINER_NAME}:${TEST_DIR}/test_results.log" tests/ 2>/dev/null || true
docker cp "${CONTAINER_NAME}:${TEST_DIR}/coverage_html" tests/ 2>/dev/null || true

# Display results summary
echo ""
if [ $RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Tests passed!${NC}"
else
    echo -e "${RED}✗ Tests failed!${NC}"
fi

echo ""
echo -e "${BLUE}Results available at:${NC}"
echo "  - HTML Coverage: file://$(pwd)/tests/coverage_html/index.html"
echo "  - Test Log:      $(pwd)/tests/test_results.log"
echo "  - JUnit XML:     $(pwd)/tests/junit.xml"
echo ""

exit $RESULT
