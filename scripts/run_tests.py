#!/usr/bin/env python3
"""
Test Runner Script

Runs the complete Vectra test suite with comprehensive reporting.
Generates test reports in multiple formats (terminal, JSON, XML, HTML coverage).

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py --unit       # Run only unit tests
    python run_tests.py --quick      # Skip slow/integration tests
    python run_tests.py --coverage   # Generate coverage report

Author: Vectra Project
License: AGPL-3.0
"""

import subprocess
import sys
import os
import json
from pathlib import Path
from datetime import datetime


def run_tests(args=None):
    """
    Run test suite with pytest.
    
    Args:
        args: Additional pytest arguments
    """
    test_dir = Path(__file__).parent / "tests"
    
    # Base pytest command with standard options
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_dir),
        "-v",
        "--tb=short",
        "--cov=app",
        "--cov-report=term-missing",
        "--cov-report=html:tests/coverage_html",
        "--cov-report=json:tests/coverage.json",
        "--cov-report=xml:tests/coverage.xml",
        "--junitxml=tests/junit.xml",
        "--log-cli=true",
        "--log-cli-level=INFO",
        "--log-file=tests/test_results.log",
        "--log-file-level=DEBUG",
    ]
    
    # Add custom arguments
    if args:
        if "--unit" in args:
            # Run only unit tests (fast, no database required)
            cmd.extend(["-m", "unit"])
        
        if "--quick" in args:
            # Skip slow and integration tests
            cmd.extend(["-m", "not slow and not integration"])
        
        if "--coverage" in args:
            cmd.append("--cov-report=html:tests/coverage_html")
        
        # Pass through any other arguments
        other_args = [arg for arg in args if not arg.startswith("--")]
        cmd.extend(other_args)
    
    print("=" * 70)
    print(f"Vectra Test Suite - {datetime.now().isoformat()}")
    print("=" * 70)
    print(f"Command: {' '.join(cmd)}\n")
    
    # Run tests
    result = subprocess.run(cmd)
    
    return result.returncode


def generate_report():
    """Generate summary report from test results."""
    test_dir = Path(__file__).parent / "tests"
    
    # Try to read coverage JSON
    coverage_file = test_dir / "coverage.json"
    if coverage_file.exists():
        with open(coverage_file) as f:
            coverage_data = json.load(f)
            total_coverage = coverage_data.get("totals", {}).get("percent_covered", 0)
            print(f"\nTotal Coverage: {total_coverage:.1f}%")
    
    # Try to read junit XML
    junit_file = test_dir / "junit.xml"
    if junit_file.exists():
        # Simple XML parsing without external dependencies
        with open(junit_file) as f:
            content = f.read()
            
        # Extract test counts
        import re
        tests_match = re.search(r'tests="(\d+)"', content)
        failures_match = re.search(r'failures="(\d+)"', content)
        errors_match = re.search(r'errors="(\d+)"', content)
        
        if tests_match:
            tests = int(tests_match.group(1))
            failures = int(failures_match.group(1)) if failures_match else 0
            errors = int(errors_match.group(1)) if errors_match else 0
            passed = tests - failures - errors
            
            print(f"\nTest Results:")
            print(f"  Total:   {tests}")
            print(f"  Passed:  {passed}")
            print(f"  Failed:  {failures}")
            print(f"  Errors:  {errors}")
    
    print("\nDetailed results:")
    print(f"  - Log:      tests/test_results.log")
    print(f"  - Coverage: tests/coverage_html/index.html")
    print(f"  - JUnit:    tests/junit.xml")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]
    exit_code = run_tests(args)
    generate_report()
    sys.exit(exit_code)
