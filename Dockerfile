FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# System deps
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
     libpq-dev \
     postgresql-client \
  && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ---- Development image ----
FROM base AS development

COPY . .

RUN chmod +x /usr/src/app/entrypoint.sh

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---- Production image ----
FROM base AS production

COPY . .

RUN chmod +x /usr/src/app/entrypoint.sh

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]

CMD ["gunicorn","config.wsgi:application","--bind", "0.0.0.0:8000","--workers", "2","--threads", "2","--timeout", "60"]
