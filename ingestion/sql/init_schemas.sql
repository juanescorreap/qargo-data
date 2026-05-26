CREATE SCHEMA IF NOT EXISTS ingestion;
CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS ingestion.watermarks (
    source_name       TEXT PRIMARY KEY,
    last_loaded_date  DATE NOT NULL,
    updated_at        TIMESTAMPTZ DEFAULT now()
);
