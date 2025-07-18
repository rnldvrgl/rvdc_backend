FROM python:3.13.3-alpine

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

# Start Django server
CMD [ "python", "manage.py", "runserver", "0.0.0.0:8000" ]