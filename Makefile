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

migrate-full:
	$(ENV) && source .venv/bin/activate && python ingestion/run.py --full-refresh
	$(ENV) && $(DBT) run --full-refresh
