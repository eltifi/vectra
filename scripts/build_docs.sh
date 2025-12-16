#!/bin/bash

###############################################################################
# Vectra Documentation Builder
#
# Comprehensive documentation build and management script
#
# @file build_docs.sh
# @author Vectra Project
# @date 2025-12-12
# @version 1.0
#
# Usage:
#   ./build_docs.sh                    Build documentation
#   ./build_docs.sh --serve            Build and serve documentation
#   ./build_docs.sh --clean            Remove generated documentation
#   ./build_docs.sh --validate         Validate documentation
#   ./build_docs.sh --help             Show help message
#
# @details
# This script provides convenient commands for:
# - Building Doxygen documentation with proper output formatting
# - Serving documentation locally via HTTP
# - Cleaning generated files
# - Validating documentation structure
# - Analyzing code quality
#
# Requirements:
# - Doxygen (install with: brew install doxygen)
# - Python 3.8+ (for serving and analysis)
# - GNU Make or similar
###############################################################################

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="${SCRIPT_DIR}"
DOCS_DIR="${BACKEND_ROOT}/docs"
HTML_DIR="${DOCS_DIR}/html"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if Doxygen is installed
check_doxygen() {
    if ! command -v doxygen &> /dev/null; then
        print_error "Doxygen not found. Install with: brew install doxygen"
        return 1
    fi
    print_success "Doxygen $(doxygen --version)"
    return 0
}

# Check if Python is available
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found"
        return 1
    fi
    print_success "Python 3 available"
    return 0
}

# Build documentation
build_docs() {
    print_header "Building Doxygen Documentation"
    
    if ! check_doxygen; then
        return 1
    fi
    
    cd "${BACKEND_ROOT}"
    
    print_warning "Generating documentation from source code..."
    
    if doxygen Doxyfile > /dev/null 2>&1; then
        print_success "Documentation build completed"
        echo ""
        echo "Output location: ${HTML_DIR}"
        echo ""
        return 0
    else
        print_error "Doxygen build failed"
        return 1
    fi
}

# Clean documentation
clean_docs() {
    print_header "Cleaning Generated Documentation"
    
    if [ -d "${DOCS_DIR}" ]; then
        rm -rf "${DOCS_DIR}"
        print_success "Documentation cleaned"
    else
        print_warning "No documentation directory found"
    fi
}

# Validate documentation
validate_docs() {
    print_header "Validating Documentation Structure"
    
    checks=0
    passed=0
    
    # Check Doxyfile
    checks=$((checks + 1))
    if [ -f "${BACKEND_ROOT}/Doxyfile" ]; then
        print_success "Doxyfile exists"
        passed=$((passed + 1))
    else
        print_error "Doxyfile not found"
    fi
    
    # Check mainpage
    checks=$((checks + 1))
    if [ -f "${BACKEND_ROOT}/Doxyfile.mainpage" ]; then
        print_success "Doxyfile.mainpage exists"
        passed=$((passed + 1))
    else
        print_error "Doxyfile.mainpage not found"
    fi
    
    # Check README
    checks=$((checks + 1))
    if [ -f "${BACKEND_ROOT}/README.md" ]; then
        print_success "README.md exists"
        passed=$((passed + 1))
    else
        print_error "README.md not found"
    fi
    
    # Check TESTING.md
    checks=$((checks + 1))
    if [ -f "${BACKEND_ROOT}/TESTING.md" ]; then
        print_success "TESTING.md exists"
        passed=$((passed + 1))
    else
        print_error "TESTING.md not found"
    fi
    
    # Check source files
    checks=$((checks + 1))
    if [ -d "${BACKEND_ROOT}/app" ]; then
        print_success "Source code directory exists"
        passed=$((passed + 1))
    else
        print_error "Source code directory not found"
    fi
    
    echo ""
    echo "Validation: ${passed}/${checks} checks passed"
    
    if [ ${passed} -eq ${checks} ]; then
        return 0
    else
        return 1
    fi
}

# Serve documentation locally
serve_docs() {
    print_header "Serving Documentation Locally"
    
    if ! check_python; then
        return 1
    fi
    
    if [ ! -d "${HTML_DIR}" ]; then
        print_error "Documentation not built. Building now..."
        if ! build_docs; then
            return 1
        fi
    fi
    
    PORT=8080
    URL="http://localhost:${PORT}"
    
    print_success "Documentation ready at: ${URL}"
    echo ""
    echo "Starting HTTP server on port ${PORT}..."
    echo "Press Ctrl+C to stop"
    echo ""
    
    cd "${HTML_DIR}"
    python3 -m http.server ${PORT}
}

# Run all operations
run_all() {
    print_header "Vectra Documentation Workflow"
    echo ""
    
    validate_docs || print_warning "Some validation checks failed"
    echo ""
    
    if check_python; then
        python3 "${BACKEND_ROOT}/docs_generator.py" --analyze
        echo ""
    fi
    
    build_docs || return 1
}

# Show usage
show_help() {
    cat << EOF
${BLUE}Vectra Documentation Builder${NC}

Usage: ./build_docs.sh [COMMAND] [OPTIONS]

Commands:
    build       Build Doxygen documentation (default)
    serve       Build and serve documentation locally on port 8080
    validate    Validate documentation structure
    clean       Remove all generated documentation
    all         Run validation, analysis, and build
    help        Show this help message

Examples:
    ./build_docs.sh                    # Build documentation
    ./build_docs.sh --serve            # Build and serve on http://localhost:8080
    ./build_docs.sh --clean            # Remove generated files
    ./build_docs.sh --validate         # Validate structure
    ./build_docs.sh --all              # Full workflow

Output:
    Generated documentation: docs/html/index.html
    Can be opened with any web browser

Requirements:
    - Doxygen: brew install doxygen
    - Python 3.8+: Usually pre-installed on macOS

EOF
}

# Main script logic
main() {
    # Parse arguments
    COMMAND="${1:-build}"
    
    case "${COMMAND}" in
        build)
            build_docs
            ;;
        serve)
            serve_docs
            ;;
        clean)
            clean_docs
            ;;
        validate)
            validate_docs
            ;;
        all)
            run_all
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: ${COMMAND}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
