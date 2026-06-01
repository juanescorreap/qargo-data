SHELL := /bin/bash
ENV  := set -a && source .env && set +a
DBT  := source .venv/bin/activate && cd qargo && dbt

dbt-debug:
	$(ENV) && $(DBT) debug

dbt-run:
	$(ENV) && $(DBT) run

dbt-test:
	$(ENV) && $(DBT) test

migrate:
	$(ENV) && source .venv/bin/activate && python ingestion/run.py

# Use this when loading a new monthly CSV — always full-refreshes silver + gold
# to avoid the incremental watermark conflict between API and CSV sources.
migrate-csv:
	$(ENV) && source .venv/bin/activate && python ingestion/run.py --source par2
	$(ENV) && $(DBT) run --full-refresh --select stg_par2 fact_sales fact_sales_by_employee

migrate-full:
	$(ENV) && source .venv/bin/activate && python ingestion/run.py --full-refresh
	$(ENV) && $(DBT) run --full-refresh

# First-time deploy after adding product_name / product_canonical_name.
# Rebuilds only the affected incremental models; table models refresh automatically.
migrate-product-granularity:
	$(ENV) && $(DBT) seed
	$(ENV) && $(DBT) run --full-refresh --select stg_par2 stg_ls2 stg_orders dim_product dim_campaign fact_sales
	$(ENV) && $(DBT) test
