# Qargo Coffee — Data Platform · Overview

Pipeline de datos end-to-end para una cadena de cafeterías multi-local. Corre cada mañana y publica un dashboard con los datos del día anterior.

---

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Fuentes | PAR POS API (SOAP Brink) + CSVs mensuales (PAR + Lightspeed) |
| Base de datos | Supabase (PostgreSQL) |
| Transformaciones | dbt-postgres |
| Dashboard | Evidence.dev |
| Deploy | Cloudflare Pages + R2 |
| CI/CD | GitHub Actions (diario 8AM UTC) |
| Tests | pytest + DuckDB |

---

## Flujo de datos

```
Fuentes → Bronze → Silver → Gold → Evidence → Cloudflare
```

3 fuentes:

- **PAR POS API** — SOAP Brink/Sales2.svc, diario (día a día), multi-tienda.
- **CSV PAR mensual** — `DDBB_{Mon}_{YY}.csv`, meses cerrados, todas las tiendas PAR en un archivo.
- **CSV Lightspeed (LS2)** — punto-coma, latin-1. Filtrar `Type IN ('SALE','UPDATE')` (el resto = ruido `TRANSITORY_*`, ~98.5% de filas). La tienda se extrae del nombre del archivo.

---

## Capas

### Ingesta (`ingestion/`)
File-based, class-based, idempotente vía watermark (`ingestion.processed_files`, PK = source_name + filename).

- `par_api.py` — cliente PAR POS SOAP async, multi-tienda.
- `run.py` — CLI CSVs: `--full-refresh`, `--source par2|ls2`.
- `loader.py` / `watermark.py` — carga idempotente.
- `sources/csv.py` — `PAR2CSVIngester`, `LS2CSVIngester`.

### dbt (`qargo/models/`)

```
bronze/sales/   → views   : bronze_par2, bronze_ls2
silver/sales/   → staging : stg_par2, stg_ls2, stg_orders
gold/dimensions/→ tables  : dim_date, dim_store, dim_product,
                            dim_destination, dim_employee, dim_campaign
gold/sales/     → facts   : fact_sales, fact_sales_by_employee,
                            fact_order, fact_sale_item
gold/insights/  → placeholder (análisis cruzados futuros)
```

### Modelo Gold

**Dimensiones**

| Tabla | Granularidad | Campos clave |
|---|---|---|
| `dim_date` | día | date_key, date, day_name, week_number, month, quarter, year, is_weekend |
| `dim_store` | tienda | store_key, store_name, royalty_rate, is_active |
| `dim_product` | 4 categorías | product_key, revenue_center_name (Beverage/Food/Retail/Other) |
| `dim_destination` | canal | destination_key, destination_name, channel (In-Store/Takeout/Drive-Thru/Delivery/Catering) |
| `dim_employee` | empleado | employee_key, employee_name |
| `dim_campaign` | campaña | dimensión de campaña (añadida en rebuild) |

**Hechos**

| Tabla | Granularidad | Métricas |
|---|---|---|
| `fact_sales` | día × tienda × categoría × canal | net_sales, tip_amount, tax_amount, discount_total. **`order_count`/`avg_ticket` deprecados (C1)** — no aditivos; ya no los consume ninguna página canónica. Sigue siendo source of truth de discount/tax/tip/net_sales. NO borrar. |
| `fact_sales_by_employee` | día × tienda × empleado | net_sales, order_count, tip_amount, tax_amount, discount_total, avg_ticket. **`order_count` arrastra el mismo defecto C1** (sin fact de orden por empleado todavía). |
| `fact_order` | **1 fila por orden real** (`source_system`, `order_id`) | order_net_sales, `order_count = 1` literal → **aditivo por construcción** (resuelve C1). LS2 keyed en `Reference` (no `Account`). Total real: 328,862 órdenes. |
| `fact_sale_item` | 1 fila por (orden × producto) | `qty` (Items Sold real, **net de devoluciones**; LS2 `Qty` real, PAR = 1.0/línea), item_net_sales (resuelve C2). Total: 566,602 units. |

---

## Dashboard (Evidence.dev)

Apunta directo al schema `gold` en Supabase (`dashboard/sources/gold/connection.yaml`). Rebuild de 8 páginas en commit `2b010fa`.

**Páginas (specs en `CLAUDE.md`):**

1. `index.md` — Executive Overview (KPI cards, time series 90d, store leaderboard MoM, labor/royalties)
2. `items_analysis.md` — análisis por producto + size breakdown
3. `stores/[store].md` — breakdown por tienda (parameterized routing, heatmap horas×días, category mix, channels)
4. `channels.md` — canales y destinos (delivery leakage, drive-thru)
5. `operations.md` — labor (up-selling, tips, productividad, discount audit)
6. `menu.md` — menú y revenue centers (attachment rate, product mix, waste placeholder)
7. `forecasting.md` — forecast ventas, YoY, weekday profiling
8. `data_quality.md` — reconciliación de fuentes, unknown tracker, freshness

Extra/legacy presentes: `forecast.md`, `performance.md`, `products.md`, `trends.md`.

Sources derivadas: `attachment_rate_monthly`, `source_by_month`, `source_summary`, `freshness_data`.

**Reglas globales:** todo en inglés, DuckDB SQL, filtros dinámicos (`<Select/>`, `<DateRange/>`), componentes Evidence (`<Value/>`, `<DataTable/>`, `<BarChart/>`, etc.).

---

## CI/CD

`.github/workflows/daily_pipeline.yml` — diario 8AM UTC (3AM EST), también manual.

```
1. Python tests
2. Load new CSV data    → bronze
3. Ingest PAR API data  → bronze (ayer)
4. dbt run              → silver + gold
5. dbt test
6. Evidence build
7. Offload WASM         → R2
8. Deploy               → Cloudflare Pages
```

**Secrets:** `SUPABASE_DB_URL`, `PAR_ACCESS_TOKEN`, `PAR_LOCATION_TOKEN`, `PAR_ENDPOINT`, `PAR_STORE_NAME`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `R2_PUBLIC_URL`. Multi-tienda: `PAR_LOCATION_TOKEN_{NOMBRE}` por local.

---

## Operación mensual de CSVs

`data/` está en `.gitignore` (CSVs solo local). El API cubre el día a día; los CSV cubren meses ya cerrados. No actualizar el CSV del mes en curso.

Carga de un CSV mensual:

1. Borrar watermark si ya fue cargado: `DELETE FROM ingestion.processed_files WHERE source_name='par2' AND filename='DDBB_May_26.csv';`
2. Colocar CSV en `data/` con nombre correcto → `make migrate-csv`
3. Verificar con `SELECT max(date), sum(net_sales) ...`

`--full-refresh` obligatorio: el API ya movió el watermark incremental, sin él el CSV se ignora silenciosamente para los últimos días del mes.

---

## Desarrollo local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m pytest tests/ -v          # tests
python ingestion/run.py             # ingesta CSV
python ingestion/par_api.py --store SANDBOX --dry-run
make dbt-debug && make dbt-run && make dbt-test
```

---

## Tests

333 tests, 0 fallos (+1 skipped: regression de credencial filtrada, inerte por defecto). dbt: 57 PASS incl. tests singulares de aditividad C1/C2 (`assert_fact_order_additive`, `assert_fact_sale_item_qty_additive`, `assert_fact_sale_item_has_parent_order`).

```
tests/ci/          workflow structure, secrets, embedded Python
tests/dbt/         lógica SQL (DuckDB, sin conexión a BD)
tests/ingestion/   ingestores CSV, watermark, loader
```

---

## Estado actual (última sesión: 2026-06-25)

Dos epics cerrados. Detalle en los reports sin commitear (`AUDIT.md`, `DIAGNOSIS_C1_C2.md`, `FACT_ORDER_BUILD.md`, `FACT_SALE_ITEM_BUILD.md`, `DASHBOARD_CUTOVER.md`, `SECURITY_FORENSICS_REPORT.md`, `REMEDIATION_REPORT.md`).

### ✅ Epic seguridad (C6 + C7) — CERRADO, verificado
- Password Supabase filtrado en working-tree `connection.yaml` → revertido a placeholders `${SUPABASE_*}`.
- `logs/dbt.log` (filtraba host/user/port/db) **purgado de los 55 commits + force-push** al remote público.
- Credencial **rotada**, verificada en dos direcciones (nueva autentica `make dbt-debug` OK; vieja rechazada por test `c06d730`).
- Causa raíz: password en 3 homes desincronizados. Fix: `~/.dbt/profiles.yml` → `env_var()`, `.env` es single source of truth. Ver memoria `credential-topology`.
- C6: `verify=True` en cliente PAR (`par_api.py`).

### ✅ Epic corrección de datos (C1 + C2) — CERRADO en modelo + dashboard
- **C1** (`order_count` no aditivo, double-counting): nuevo `fact_order`. Inflado 524,238 → real **328,862** (−37%).
- **C2** (Items Sold no eran ítems): nuevo `fact_sale_item` con `Qty` real de LS2. Items Sold = `sum(qty)` = **566,602**, net de devoluciones.
- Bug LS2 hallado: order_id estaba en `Account` (agrupa ~5.5 órdenes) → `fact_order` usa `Reference`.
- 8 páginas canónicas migradas a los nuevos facts.

### Backlog pendiente (nada bloqueante)

| Item | Sev | Falta |
|---|---|---|
| `SUPABASE_SSL_CA` | MED | Código scaffolded (`48350d8`). Usuario debe pegar el CA PEM real del pooler Supabase en `.env` + crear el GitHub secret, si no el build Evidence con TLS estricto falla (`self-signed certificate in certificate chain`). **NO revertir a `false`**. |
| GitHub secret `SUPABASE_DB_URL` | ASK | User-attested rotado, no verificable por mí. Reconfirmar que tiene el pw nuevo URL-encoded o el CI diario 8AM falla. |
| `operations.md` | LOW | Sigue en `fact_sales_by_employee.order_count` — mismo defecto C1, sin fact de orden por empleado todavía. |
| M8 páginas legacy | LOW | `forecast.md`, `performance.md`, `products.md` — duplicados aún sobre `fact_sales.order_count` inflado. Recomendado **borrar**. |
| **C3** (API sin producto/categoría) | P0-concept | Filas API → `product_key=0 (UNKNOWN)`; `Item Name=None`, `Revenue Center=DayPartId`. Sin tocar. Items/Category/Attachment basura para fechas solo-API. |
| **C4** (dos writers en `raw_par2`) | P0 | DELETE con semánticas incompatibles → clobber silencioso CSV↔API. Sin tocar. |
| **C5** (watermark descarta backfill) | P0 | Incremental append+watermark pierde data tardía en silencio. Sin tocar. |
| API tax dup | — | Tax order-level copiado por entry → `sum(tax)` multiplicado. Flagged, sin tocar. |

### Repo snapshot
Working tree limpio salvo docs/data sin commitear: los reports `.md` de arriba + `scripts/` + xlsx/csv de análisis ad-hoc (Grand Prairie, Westerville, Tampa, food sales). Sin código sin commitear. `main` sincronizado con origin @ `38eb355`. `forecasting/` = placeholder vacío.
