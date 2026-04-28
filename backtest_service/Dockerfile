FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

# System deps for numpy/pandas/vectorbt compiled extensions + healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy all workspace members needed by uv.lock
COPY pyproject.toml uv.lock README.md ./
COPY libs/ptc-cli/          libs/ptc-cli/
COPY libs/ginlix_data_sdk/  libs/ginlix_data_sdk/
COPY libs/ginlix_backtest/  libs/ginlix_backtest/

# Install only backtest-related deps (skip LangChain/browser etc.)
RUN uv sync --no-dev --frozen

# Copy service code
COPY backtest_service ./backtest_service

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "backtest_service.main:app", \
     "--host", "0.0.0.0", "--port", "8001"]
