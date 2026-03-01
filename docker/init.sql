-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- =============================================================================
-- TABLE: raw_logs
-- Purpose: Store all incoming logs in their raw form
-- Optimization: TimescaleDB hypertable for time-series queries
-- =============================================================================
CREATE TABLE raw_logs (
    id SERIAL PRIMARY KEY,
    log_type VARCHAR(50) NOT NULL DEFAULT 'web',
    timestamp TIMESTAMPTZ NOT NULL,
    ip INET,
    method VARCHAR(10),
    endpoint VARCHAR(500),
    status INTEGER,
    response_time_ms FLOAT,
    user_agent TEXT,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('raw_logs', 'timestamp');

-- Indexes for fast queries
CREATE INDEX idx_raw_logs_timestamp ON raw_logs(timestamp DESC);
CREATE INDEX idx_raw_logs_type ON raw_logs(log_type);
CREATE INDEX idx_raw_logs_ip ON raw_logs(ip);
CREATE INDEX idx_raw_logs_status ON raw_logs(status);
CREATE INDEX idx_raw_logs_data_gin ON raw_logs USING GIN(data);

-- =============================================================================
-- TABLE: alerts
-- Purpose: Store detection alerts from rules and ML
-- =============================================================================
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    source VARCHAR(50) NOT NULL CHECK (source IN ('rule', 'ml', 'hybrid')),
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    description TEXT,
    log_ids INTEGER[],
    ip INET,
    timestamp TIMESTAMPTZ NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_timestamp ON alerts(timestamp DESC);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_type ON alerts(alert_type);
CREATE INDEX idx_alerts_ip ON alerts(ip);
CREATE INDEX idx_alerts_source ON alerts(source);

-- =============================================================================
-- TABLE: ml_predictions
-- Purpose: Store ML model predictions for each log
-- =============================================================================
CREATE TABLE ml_predictions (
    id SERIAL PRIMARY KEY,
    log_id INTEGER REFERENCES raw_logs(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    anomaly_score FLOAT NOT NULL,
    is_anomaly BOOLEAN NOT NULL,
    features JSONB,
    shap_values JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ml_predictions_log_id ON ml_predictions(log_id);
CREATE INDEX idx_ml_predictions_model ON ml_predictions(model_name, model_version);
CREATE INDEX idx_ml_predictions_is_anomaly ON ml_predictions(is_anomaly);
CREATE INDEX idx_ml_predictions_created_at ON ml_predictions(created_at DESC);

-- =============================================================================
-- TABLE: model_runs
-- Purpose: Track ML model training runs (MLflow metadata)
-- =============================================================================
CREATE TABLE model_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(100) UNIQUE NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    hyperparameters JSONB,
    metrics JSONB,
    artifacts_path VARCHAR(500),
    status VARCHAR(50) CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_model_runs_run_id ON model_runs(run_id);
CREATE INDEX idx_model_runs_model ON model_runs(model_name);
CREATE INDEX idx_model_runs_status ON model_runs(status);
CREATE INDEX idx_model_runs_created_at ON model_runs(created_at DESC);

-- =============================================================================
-- TABLE: feedback
-- Purpose: Store human-in-the-loop feedback (Goal C)
-- =============================================================================
CREATE TABLE feedback (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE CASCADE,
    user_id VARCHAR(100),
    label VARCHAR(50) CHECK (label IN ('true_positive', 'false_positive', 'false_negative')),
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_feedback_alert_id ON feedback(alert_id);
CREATE INDEX idx_feedback_label ON feedback(label);
CREATE INDEX idx_feedback_created_at ON feedback(created_at DESC);

-- =============================================================================
-- VIEWS: Useful queries as views
-- =============================================================================

-- Recent alerts (last 24h)
CREATE VIEW recent_alerts AS
SELECT 
    id,
    alert_type,
    severity,
    source,
    confidence,
    ip,
    timestamp,
    created_at
FROM alerts
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;

-- Anomaly summary by hour
CREATE VIEW anomaly_hourly_summary AS
SELECT 
    date_trunc('hour', timestamp) AS hour,
    COUNT(*) AS total_logs,
    SUM(CASE WHEN EXISTS (
        SELECT 1 FROM ml_predictions mp 
        WHERE mp.log_id = raw_logs.id AND mp.is_anomaly = true
    ) THEN 1 ELSE 0 END) AS anomalies,
    ROUND(
        100.0 * SUM(CASE WHEN EXISTS (
            SELECT 1 FROM ml_predictions mp 
            WHERE mp.log_id = raw_logs.id AND mp.is_anomaly = true
        ) THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) AS anomaly_rate
FROM raw_logs
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour DESC;
