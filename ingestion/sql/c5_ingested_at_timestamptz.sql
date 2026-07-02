-- C5 (Option 1): make bronze _ingested_at a proper load-time watermark column.
-- The column already existed (populated by the writers) as `timestamp without time
-- zone`; C5 promotes it to timestamptz + DEFAULT now() so silver/gold can use it as
-- the incremental high-water mark. Existing values are naive UTC → interpreted AT
-- TIME ZONE 'UTC'. bronze_par2 / bronze_ls2 are views over these tables (select *),
-- so they must be dropped before the type change and rebuilt by dbt afterwards.
--
-- Idempotent-ish: re-running the ALTER TYPE on an already-timestamptz column is a
-- no-op cast. Run `dbt run --select bronze_par2 bronze_ls2` after this.

DROP VIEW IF EXISTS bronze.bronze_par2;
DROP VIEW IF EXISTS bronze.bronze_ls2;

ALTER TABLE bronze.raw_par2_csv
    ALTER COLUMN "_ingested_at" TYPE timestamptz USING "_ingested_at" AT TIME ZONE 'UTC',
    ALTER COLUMN "_ingested_at" SET DEFAULT now();

ALTER TABLE bronze.raw_par2_api
    ALTER COLUMN "_ingested_at" TYPE timestamptz USING "_ingested_at" AT TIME ZONE 'UTC',
    ALTER COLUMN "_ingested_at" SET DEFAULT now();

ALTER TABLE bronze.raw_ls2
    ALTER COLUMN "_ingested_at" TYPE timestamptz USING "_ingested_at" AT TIME ZONE 'UTC',
    ALTER COLUMN "_ingested_at" SET DEFAULT now();
