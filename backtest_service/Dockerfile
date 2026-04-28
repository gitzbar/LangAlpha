FROM python:3.12-slim

WORKDIR /app

# System deps for numpy/pandas compiled extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./
COPY libs/ginlix_data_sdk ./libs/ginlix_data_sdk
COPY libs/ginlix_backtest ./libs/ginlix_backtest

RUN pip install uv && \
    uv sync --no-dev --frozen

# Copy service code
COPY backtest_service ./backtest_service

# Data snapshots are mounted at runtime via docker-compose volume
# ENV so the SDK can find them when DATA_ROOT is overridden
ENV DATA_ROOT=/data

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "backtest_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
