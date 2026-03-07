# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python application
FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock .python-version ./
COPY stochastic_warfare/ stochastic_warfare/
COPY api/ api/
COPY data/ data/
RUN uv sync --extra api --no-dev
COPY --from=frontend-build /app/frontend/dist frontend/dist/
EXPOSE 8000
CMD ["uv", "run", "python", "-m", "api"]
