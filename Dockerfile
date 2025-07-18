FROM python:3.13.3-alpine AS base

# Set work directory
WORKDIR /usr/src/app

# Prevent Python from writing .pyc files to disc and enable stdout/stderr logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy project files
COPY . .

# Development stage
FROM base AS development
CMD [ "python", "manage.py", "runserver", "0.0.0.0:8000" ]

# Production stage
FROM base AS production
RUN chmod +x /usr/src/app/entrypoint.sh
ENTRYPOINT ["/usr/src/app/entrypoint.sh"]
CMD [ "gunicorn", "project.wsgi:application", "--bind", "0.0.0.0:8000" ]