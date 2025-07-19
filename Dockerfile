# Base image for building and installing dependencies
FROM python:3.13.3-alpine AS base

WORKDIR /usr/src/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache build-base libpq postgresql-dev

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Development stage (not used in production)
FROM base AS development
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# 🔥 Production stage (this is what matters)
FROM python:3.13.3-alpine AS production

WORKDIR /usr/src/app

RUN apk add --no-cache build-base libpq postgresql-dev

# Copy requirements and install them again (must do this in this stage!)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy everything else
COPY . .

# Make sure entrypoint script is executable
RUN chmod +x /usr/src/app/entrypoint.sh

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]