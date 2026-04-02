#!/bin/bash
# Start MLflow tracking server

echo "🚀 Starting MLflow Tracking Server..."

mlflow server \
    --backend-store-uri sqlite:///mlruns/mlflow.db \
    --default-artifact-root ./mlruns \
    --host 0.0.0.0 \
    --port 5000

# Acesso: http://localhost:5000
