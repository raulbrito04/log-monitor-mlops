# test_mlflow.py

import mlflow

# Set tracking URI
mlflow.set_tracking_uri("http://localhost:5000")

# Create test experiment
mlflow.set_experiment("test-experiment")

# Log test run
with mlflow.start_run(run_name="test-run"):
    mlflow.log_param("test_param", 42)
    mlflow.log_metric("test_metric", 0.95)
    
print("✓ MLflow funcionando!")
print("✓ Ver em: http://localhost:5000")
