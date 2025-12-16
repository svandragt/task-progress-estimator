FROM python:3.13-slim

RUN apt-get update -y && apt-get install -y --no-install-recommends \
      ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
EXPOSE 8501

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash","-lc","\
  uv run streamlit run main.py \
    --server.headless=${STREAMLIT_SERVER_HEADLESS:-true} \
    --server.address=${HOST:-0.0.0.0} \
    --server.port=${PORT:-8501} \
    --browser.gatherUsageStats=${STREAMLIT_BROWSER_GATHER_USAGE_STATS:-false} \
"]
