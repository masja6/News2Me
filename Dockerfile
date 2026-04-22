FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (for layer caching)
COPY pyproject.toml .
# Trick to install dependencies without the whole package
RUN pip install --no-cache-dir build && pip install .

# Copy application files
COPY . .

# Ensure data directory exists
RUN mkdir -p data

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD sh -c "uvicorn newstome.ui:app --host 0.0.0.0 --port ${PORT:-8000}"
