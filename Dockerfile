FROM python:alpine

# Set production environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENVIRONMENT=production

# Install build dependencies only for compilation
RUN apk add --no-cache --virtual .build-deps \
    build-base \
    postgresql-dev \
    gdal-dev \
    geos-dev \
    proj-dev

# Install runtime dependencies
RUN apk add --no-cache \
    postgresql-libs \
    gdal \
    geos \
    proj
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Remove build dependencies after installation
RUN apk del .build-deps

# Copy the rest of the app
COPY . .

# Command for production with proper settings
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
