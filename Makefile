.PHONY: test test-unit test-quick test-coverage test-verbose test-report test-watch help

# Vectra Test Commands
# Usage: make test, make test-unit, etc.

help:
	@echo "Vectra Test Commands"
	@echo "====================="
	@echo ""
	@echo "  make test              Run all tests"
	@echo "  make test-unit         Run unit tests only (fast)"
	@echo "  make test-quick        Skip slow/integration tests"
	@echo "  make test-coverage     Generate coverage report"
	@echo "  make test-verbose      Run with verbose output"
	@echo "  make test-report       Show test report summary"
	@echo "  make test-watch        Run tests in watch mode"
	@echo "  make test-docker       Run tests in Docker container"
	@echo ""

# Run all tests
test:
	@echo "Running all tests..."
	python -m pytest tests/ -v --tb=short \
		--cov=app --cov-report=term-missing \
		--cov-report=html:tests/coverage_html \
		--cov-report=json:tests/coverage.json \
		--cov-report=xml:tests/coverage.xml \
		--junitxml=tests/junit.xml \
		--log-file=tests/test_results.log

# Run only unit tests (fast)
test-unit:
	@echo "Running unit tests only..."
	python -m pytest tests/ -v -m unit --tb=short \
		--log-file=tests/test_results.log

# Skip slow and integration tests
test-quick:
	@echo "Running quick tests (excluding slow/integration)..."
	python -m pytest tests/ -v -m "not slow and not integration" \
		--log-file=tests/test_results.log

# Generate comprehensive coverage report
test-coverage:
	@echo "Generating coverage report..."
	python -m pytest tests/ -v \
		--cov=app --cov-report=term-missing \
		--cov-report=html:tests/coverage_html \
		--cov-report=json:tests/coverage.json
	@echo ""
	@echo "Coverage report generated:"
	@echo "  HTML: file://$$(pwd)/tests/coverage_html/index.html"

# Verbose test output
test-verbose:
	@echo "Running tests with verbose output..."
	python -m pytest tests/ -vv --tb=long --capture=no \
		--log-cli=true --log-cli-level=DEBUG

# Show test report
test-report:
	@echo "Test Results"
	@echo "============"
	@if [ -f tests/test_results.log ]; then \
		echo ""; \
		tail -30 tests/test_results.log; \
	else \
		echo "No test results found. Run 'make test' first."; \
	fi

# Watch mode (requires pytest-watch)
test-watch:
	@echo "Running tests in watch mode..."
	ptw tests/ -- -v --tb=short

# Run tests in Docker
test-docker:
	@echo "Running tests in Docker container..."
	./scripts/run_tests.sh

# Run specific test file
test-file:
	@read -p "Enter test file path (e.g., tests/test_api.py): " testfile; \
	python -m pytest $$testfile -v --tb=short

# Run specific test
test-specific:
	@read -p "Enter test name (e.g., TestSegmentsEndpoint::test_segments_returns_json): " testname; \
	python -m pytest tests/ -v -k "$$testname" --tb=short

# Clean test artifacts
test-clean:
	@echo "Cleaning test artifacts..."
	rm -rf tests/__pycache__ tests/.pytest_cache
	rm -rf tests/coverage_html tests/.coverage
	rm -f tests/coverage.json tests/coverage.xml tests/junit.xml
	rm -f tests/test_results.log
	@echo "Done!"

# Install test dependencies
test-install:
	@echo "Installing test dependencies..."
	pip install -r requirements-test.txt

# Run linting
lint:
	@echo "Running code quality checks..."
	pylint app/ --exit-zero
	mypy app/ --ignore-missing-imports --no-error-summary --exit-zero

# Format code
format:
	@echo "Formatting code..."
	black app/ tests/

# Full CI pipeline
ci: lint test test-report
	@echo ""
	@echo "✓ CI pipeline complete!"
