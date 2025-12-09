# --- Base image: common setup for both dev and prod ---
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# System deps needed for compiling wheels and postgres tools
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt

# ---- Development image ----
FROM base AS development

# Copy full source for local development
COPY . .

# Run Django devserver
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---- Production image ----
FROM base AS production

# Copy project files
COPY . .

# Ensure entrypoint is executable
RUN chmod +x /usr/src/app/entrypoint.sh

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
