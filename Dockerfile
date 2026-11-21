FROM node:24-bookworm-slim AS web
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY backend/ backend/
COPY --from=web /app/frontend/dist frontend/dist
EXPOSE 8000
CMD [".venv/bin/uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
