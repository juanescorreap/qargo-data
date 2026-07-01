-- C4 historical migration: copy existing bronze.raw_par2 rows into the new
-- per-source split tables, partitioned by _source_system. One-time, idempotent
-- only against EMPTY targets (guard below). entry_id stays NULL for historical
-- rows (the old shared table never had it).
--
-- The old bronze.raw_par2 is intentionally left intact (read-only) for
-- transition/comparison and is pending user-confirmed deprecation — do NOT drop
-- or truncate it here.

DO $$
DECLARE csv_n bigint; api_n bigint;
BEGIN
    SELECT count(*) INTO csv_n FROM bronze.raw_par2_csv;
    SELECT count(*) INTO api_n FROM bronze.raw_par2_api;
    IF csv_n <> 0 OR api_n <> 0 THEN
        RAISE EXCEPTION 'Targets not empty (csv=%, api=%) — abort to avoid duplicate migration', csv_n, api_n;
    END IF;
END $$;

INSERT INTO bronze.raw_par2_csv (
    "Location","Date","Employee Name","Item ID","Item Name","Item PLU","Price",
    "Discount Total","Promotion Total","Taxes","Net Sales","Gross Sales",
    "Total Sales","Revenue Center","Has Employee Discount","Destination",
    "Voided","Has Customer","Is Modifier","Order ID","_source_file",
    "_source_system","_ingested_at")
SELECT
    "Location","Date","Employee Name","Item ID","Item Name","Item PLU","Price",
    "Discount Total","Promotion Total","Taxes","Net Sales","Gross Sales",
    "Total Sales","Revenue Center","Has Employee Discount","Destination",
    "Voided","Has Customer","Is Modifier","Order ID","_source_file",
    "_source_system","_ingested_at"
FROM bronze.raw_par2
WHERE "_source_system" = 'par2';

INSERT INTO bronze.raw_par2_api (
    "Location","Date","Employee Name","Item ID","Item Name","Item PLU","Price",
    "Discount Total","Promotion Total","Taxes","Net Sales","Gross Sales",
    "Total Sales","Revenue Center","Has Employee Discount","Destination",
    "Voided","Has Customer","Is Modifier","Order ID","_source_file",
    "_source_system","_ingested_at")
SELECT
    "Location","Date","Employee Name","Item ID","Item Name","Item PLU","Price",
    "Discount Total","Promotion Total","Taxes","Net Sales","Gross Sales",
    "Total Sales","Revenue Center","Has Employee Discount","Destination",
    "Voided","Has Customer","Is Modifier","Order ID","_source_file",
    "_source_system","_ingested_at"
FROM bronze.raw_par2
WHERE "_source_system" = 'par_api';

-- Post-check (run manually):
--   SELECT (SELECT count(*) FROM bronze.raw_par2_csv) AS csv,
--          (SELECT count(*) FROM bronze.raw_par2_api) AS api,
--          (SELECT count(*) FROM bronze.raw_par2)     AS old_total;
-- Expect csv + api = old_total.
