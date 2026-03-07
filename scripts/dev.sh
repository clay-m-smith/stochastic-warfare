#!/usr/bin/env bash
set -e
trap 'kill 0' EXIT

echo "Starting API server on http://localhost:8000..."
uv run uvicorn api.main:app --reload &

echo "Starting frontend dev server on http://localhost:5173..."
cd frontend && npm run dev &

wait
