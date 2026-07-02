-- C4 fix: split bronze.raw_par2 into per-source physical tables so the two
-- writers (CSV loader, PAR API) can never clobber each other.
--   raw_par2_csv  <- Writer B only (ingestion/run.py -> FileBasedLoader / PAR2CSVIngester)
--   raw_par2_api  <- Writer A only (ingestion/par_api.py -> write_raw_par2)
-- Both carry the full 23-column raw_par2 schema (UNION-compatible) plus an
-- `entry_id` column used only by the API source for line-level idempotency
-- (NULL for CSV rows). stg_par2 UNIONs the two with CSV-over-API precedence.
--
-- Idempotent — safe to re-run.

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.raw_par2_csv (
    "Location"              text,
    "Date"                  date,
    "Employee Name"         text,
    "Item ID"               bigint,
    "Item Name"             text,
    "Item PLU"              double precision,
    "Price"                 double precision,
    "Discount Total"        double precision,
    "Promotion Total"       double precision,
    "Taxes"                 double precision,
    "Net Sales"             double precision,
    "Gross Sales"           double precision,
    "Total Sales"           double precision,
    "Revenue Center"        text,
    "Has Employee Discount" boolean,
    "Destination"           text,
    "Voided"                boolean,
    "Has Customer"          boolean,
    "Is Modifier"           boolean,
    "Order ID"              text,
    "_source_file"          text,
    "_source_system"        text,
    "_ingested_at"          timestamptz DEFAULT now(),
    "entry_id"              text   -- always NULL for CSV; present for schema parity
);

CREATE TABLE IF NOT EXISTS bronze.raw_par2_api (
    "Location"              text,
    "Date"                  date,
    "Employee Name"         text,
    "Item ID"               bigint,
    "Item Name"             text,
    "Item PLU"              double precision,
    "Price"                 double precision,
    "Discount Total"        double precision,
    "Promotion Total"       double precision,
    "Taxes"                 double precision,
    "Net Sales"             double precision,
    "Gross Sales"           double precision,
    "Total Sales"           double precision,
    "Revenue Center"        text,
    "Has Employee Discount" boolean,
    "Destination"           text,
    "Voided"                boolean,
    "Has Customer"          boolean,
    "Is Modifier"           boolean,
    "Order ID"              text,
    "_source_file"          text,
    "_source_system"        text,
    "_ingested_at"          timestamptz DEFAULT now(),
    "entry_id"              text   -- PAR OrderEntry Id; unique per line within an order
);

CREATE INDEX IF NOT EXISTS idx_raw_par2_csv_date ON bronze.raw_par2_csv ("Date");
CREATE INDEX IF NOT EXISTS idx_raw_par2_api_date ON bronze.raw_par2_api ("Date");
