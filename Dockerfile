# --- Base image: common setup for both dev and prod ---
FROM python:3.12.3-alpine AS base

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System packages (shared)
RUN apk add --no-cache build-base postgresql-dev

# Install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# --- Dev stage: used only in docker-compose.override.yml ---
FROM base AS development

# Copy full source code after installing dependencies
COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# --- Production stage: for final deployment ---
FROM python:3.13.3-alpine AS production

WORKDIR /usr/src/app

# Install system deps again (no cache sharing across stages)
RUN apk add --no-cache build-base postgresql-dev

# Copy requirements and install
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app code
COPY . .

# Ensure entrypoint is executable
RUN chmod +x /usr/src/app/entrypoint.sh

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
