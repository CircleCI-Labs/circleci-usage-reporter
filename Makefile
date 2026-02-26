.PHONY: help install install-cli install-dev lint test clean all build

# Default target
help:
	@echo "Available commands:"
	@echo "  install        Install all dependencies"
	@echo "  install-cli    Install CLI in editable mode"
	@echo "  install-dev    Install CLI in editable mode + dev/test dependencies"
	@echo "  build          Build distribution packages"
	@echo "  lint           Run all linting checks"
	@echo "  test           Run tests with coverage"
	@echo "  clean          Clean up generated files"
	@echo "  all            Run lint and test"

# Install dependencies
install:
	pip3 install --upgrade pip
	pip3 install -r requirements.txt

# Install CLI system-wide in editable mode
install-cli: install
	pip3 install -e .

# Install CLI in editable mode with dev/test dependencies
install-dev: install
	pip3 install -e .
	pip3 install pytest pytest-cov flake8

# Build distribution packages
build:
	python -m build

# Run all linting checks
lint:
	@echo "Running flake8..."
	flake8 src/
	@echo "✅ All linting checks passed!"

# Run tests
test:
	@echo "Running tests with pytest..."
	python -m pytest tests/ -v
	@echo "✅ Tests completed!"

# Clean up generated files
clean:
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf test-results/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete

# Run everything
all: lint test