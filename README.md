# Qargo Coffee — Data Platform

Pipeline de datos end-to-end para una cadena de cafeterías con múltiples locales. Corre automáticamente cada mañana y publica un dashboard con los datos del día anterior.

---

## Stack

| Capa | Tecnología |
|---|---|
| Fuentes | PAR POS API (Brink/SOAP) + CSVs mensuales (PAR + Lightspeed) |
| Base de datos | Supabase (PostgreSQL) |
| Transformaciones | dbt-postgres |
| Dashboard | Evidence.dev |
| Deploy | Cloudflare Pages + R2 |
| CI/CD | GitHub Actions (diario 8AM UTC) |
| Lenguaje | Python 3.12 |
| Tests | pytest + DuckDB |

---

## Flujo de datos

```
┌─────────────────────────────────────┐
│           FUENTES DE DATOS          │
│  PAR POS API  │  CSVs PAR  │  LS2   │
└──────┬────────┴─────┬──────┴───┬────┘
       │              │          │
       ▼              ▼          ▼
┌─────────────────────────────────────┐
│           BRONZE (Supabase)         │
│  raw_par2   raw_par2_entries  raw_ls2│
└──────────────────┬──────────────────┘
                   │  dbt
                   ▼
┌─────────────────────────────────────┐
│           SILVER                    │
│       stg_par2 + stg_ls2            │
│          └── stg_orders (view)      │
└──────────────────┬──────────────────┘
                   │  dbt
                   ▼
┌─────────────────────────────────────┐
│           GOLD                      │
│  dim_date  dim_store  dim_product   │
│  dim_destination  dim_employee      │
│  fact_sales  fact_sales_by_employee │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│        Evidence.dev Dashboard       │
│  index  │  forecast  │  /stores/*   │
└──────────────────┬──────────────────┘
                   │
                   ▼
            Cloudflare Pages
```

---

## Estructura del repositorio

```
qargo-data/
├── ingestion/              # Ingesta de datos
│   ├── par_api.py          # Cliente PAR POS SOAP (httpx async, multi-tienda)
│   ├── run.py              # CLI para ingesta de CSVs
│   ├── loader.py           # Carga idempotente con watermark
│   ├── watermark.py        # Marca de agua en Supabase
│   └── sources/
│       ├── csv.py          # Ingestores PAR CSV y Lightspeed CSV
│       └── api.py
├── qargo/                  # Proyecto dbt
│   └── models/
│       ├── bronze/sales/   # Vistas sobre tablas raw
│       ├── silver/sales/   # Staging normalizado (stg_par2, stg_ls2, stg_orders)
│       └── gold/
│           ├── dimensions/ # dim_date, dim_store, dim_product, dim_destination, dim_employee
│           └── sales/      # fact_sales, fact_sales_by_employee
├── dashboard/              # Evidence.dev
│   └── pages/              # index.md, forecast.md, stores/[store].md
├── ci/                     # Scripts de CI
│   └── r2_offload.py       # Offload de WASM grandes a Cloudflare R2
├── tests/                  # Suite de tests (pytest + DuckDB)
│   ├── ci/                 # Tests del workflow y CI
│   ├── dbt/                # Tests de lógica SQL (sin conexión a BD)
│   └── ingestion/          # Tests de ingestores
├── data/                   # CSVs históricos (no commiteados en producción)
├── docs/                   # Documentación PAR POS
└── .github/workflows/
    └── daily_pipeline.yml  # Pipeline diario
```

---

## Ingesta

### PAR POS API (`ingestion/par_api.py`)
Consume el endpoint SOAP Sales2.svc de Brink/PAR diariamente. Soporta múltiples tiendas via variables de entorno.

```bash
python ingestion/par_api.py                        # todas las tiendas, ayer
python ingestion/par_api.py --date 2026-05-27      # fecha específica
python ingestion/par_api.py --store SANDBOX --dry-run
```

### CSVs (`ingestion/run.py`)
Lee archivos históricos mensuales de `data/`. Idempotente — no reprocesa archivos ya cargados.

```bash
python ingestion/run.py               # solo archivos nuevos
python ingestion/run.py --full-refresh
```

---

## Modelo de datos (Gold)

### Dimensiones

| Tabla | Granularidad | Campos clave |
|---|---|---|
| `dim_date` | Un registro por día | date_key, date, day_name, week_number, month, quarter, year, is_weekend |
| `dim_store` | Una fila por tienda | store_key, store_name, royalty_rate, is_active |
| `dim_product` | 4 categorías fijas | product_key, revenue_center_name (Beverage/Food/Retail/Other) |
| `dim_destination` | Canal de venta | destination_key, destination_name, channel (In-Store/Takeout/Drive-Thru/Delivery/Catering) |
| `dim_employee` | Un registro por empleado | employee_key, employee_name |

### Tablas de hechos

| Tabla | Granularidad | Métricas |
|---|---|---|
| `fact_sales` | Día × tienda × categoría × canal | net_sales, order_count, tip_amount, tax_amount, discount_total, avg_ticket |
| `fact_sales_by_employee` | Día × tienda × empleado | net_sales, order_count, tip_amount, tax_amount, discount_total, avg_ticket |

---

## Pipeline CI/CD

Corre automáticamente todos los días a las **8AM UTC (3AM EST)**. También puede dispararse manualmente desde GitHub Actions.

```
1. Run Python tests
2. Load new CSV data       → bronze
3. Ingest PAR API data     → bronze  (datos de ayer)
4. dbt run                 → silver + gold
5. dbt test
6. Evidence build
7. Offload WASM → R2
8. Deploy → Cloudflare Pages
```

### Secrets requeridos en GitHub

| Secret | Descripción |
|---|---|
| `SUPABASE_DB_URL` | Connection string PostgreSQL (Supabase pooler) |
| `PAR_ACCESS_TOKEN` | Token global PAR POS |
| `PAR_LOCATION_TOKEN` | Token de ubicación (tienda única) |
| `PAR_ENDPOINT` | URL del endpoint PAR POS |
| `PAR_STORE_NAME` | Nombre de la tienda (ej. `TAMPA`) |
| `CLOUDFLARE_API_TOKEN` | Token Cloudflare para deploy |
| `CLOUDFLARE_ACCOUNT_ID` | ID de cuenta Cloudflare |
| `R2_PUBLIC_URL` | URL pública del bucket R2 |

Para múltiples tiendas, agregar `PAR_LOCATION_TOKEN_{NOMBRE}` por cada local adicional.

---

## Actualización mensual de CSVs

`data/` está en `.gitignore` — los CSVs viven solo en tu máquina local y se cargan manualmente a Supabase. El API cubre el día a día; los CSVs cubren meses completos ya cerrados.

### Cuándo usar cada fuente

| Frecuencia | Fuente | Acción |
|---|---|---|
| Diario (automático) | PAR API | CI corre solo — no requiere intervención |
| Principios de cada mes | CSV PAR mensual | Proceso manual abajo |

> **Importante:** no actualices el CSV del mes en curso semana a semana. El API ya cubre esos días. Actualiza el CSV solo cuando el mes esté cerrado.

### Proceso para cargar un CSV mensual

**Paso 1 — Borra el watermark** (solo si el archivo ya fue cargado antes)

En Supabase → SQL Editor:
```sql
DELETE FROM ingestion.processed_files
WHERE source_name = 'par2' AND filename = 'DDBB_May_26.csv';
```

**Paso 2 — Coloca el CSV en `data/`** con el nombre correcto (`DDBB_May_26.csv`) y corre:

```bash
make migrate-csv
```

Esto ejecuta en orden:
```
1. python ingestion/run.py --source par2        → bronze (raw_par2)
2. dbt run --full-refresh --select
       stg_par2                                 → silver
       fact_sales                               → gold
       fact_sales_by_employee                   → gold
```

El `--full-refresh` es obligatorio porque el API ya movió el watermark incremental al día de hoy — sin él, el CSV queda silenciosamente ignorado para los últimos días del mes.

**Paso 3 — Verifica**

```sql
SELECT max(d.date), sum(f.net_sales)
FROM gold.fact_sales f
JOIN gold.dim_date d ON f.date_key = d.date_key
WHERE d.date >= '2026-05-01';
```

---

## Desarrollo local

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Tests
python -m pytest tests/ -v

# Ingesta manual
python ingestion/run.py
python ingestion/par_api.py --store SANDBOX --dry-run

# dbt
make dbt-debug
make dbt-run
make dbt-test
```

---

## Tests

```
243 tests — 0 fallos
├── tests/ci/          workflow structure, secrets, embedded Python
├── tests/dbt/         SQL logic (DuckDB, sin conexión a BD)
└── tests/ingestion/   ingestores CSV, watermark, loader
```
