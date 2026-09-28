# ==============================================================================
# SONORA Production Multi-Stage Dockerfile
# ==============================================================================

# Build stage: Install build dependencies and generate wheels
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage: Minimal Debian image with FFmpeg & non-root user
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Install runtime system packages: FFmpeg and curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user and group
RUN groupadd -r -g 1000 sonora && \
    useradd -r -u 1000 -g sonora -d /app -s /sbin/nologin sonora

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/sonora/.local
ENV PATH=/home/sonora/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source code
COPY --chown=sonora:sonora app/ /app/app/
COPY --chown=sonora:sonora README.md /app/README.md

# Ensure data directory exists with appropriate permissions
RUN mkdir -p /app/data/temp /app/data/completed && \
    chown -R sonora:sonora /app/data

# Switch to unprivileged runtime user
USER sonora

# Expose standard FastAPI port
EXPOSE 8000

# Periodic container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Production entrypoint
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
