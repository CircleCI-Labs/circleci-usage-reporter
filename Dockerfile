# Use Python 3.13 Alpine as base image for smaller size
FROM python:3.13-alpine

# Set maintainer label
LABEL maintainer="CircleCI Labs"
LABEL description="CircleCI Usage API Reporter - Tools for extracting, processing, and visualizing CircleCI usage data"

# Set working directory
WORKDIR /app

# Install system dependencies required for Python packages
# - gcc, musl-dev: Required for compiling Python packages with C extensions
# - libffi-dev: Required for some cryptographic packages
# - build-base: Basic build tools
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    build-base \
    && rm -rf /var/cache/apk/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt ./

# Install Python dependencies
# Use pip with no-cache-dir to reduce image size
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY src/ ./src/

# Create directories for reports and artifacts
RUN mkdir -p /tmp/reports

# Set environment variables with defaults
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Create a non-root user for security
RUN addgroup -g 1001 appgroup && \
    adduser -D -u 1001 -G appgroup appuser && \
    chown -R appuser:appgroup /app /tmp/reports

# Switch to non-root user
USER appuser

# Set the default entrypoint to python
ENTRYPOINT ["python"]

# Health check (optional)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"
