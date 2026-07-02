# Due Diligence Técnica — Qargo Coffee Data Platform

> Auditoría end-to-end basada en lectura directa del código (ingesta, dbt, CI, dashboard), no solo documentación.
> Fecha: 2026-06-10.

---

## 1. Resumen ejecutivo

Plataforma funcional, bien estructurada en superficie (capas medallion, dbt multi-dominio, CI declarativo, 333 tests), construida por alguien con criterio. Pero bajo el capó tiene **defectos de corrección de datos que invalidan métricas clave del dashboard hoy**, y un modelo incremental con varios footguns silenciosos ya documentados por el propio autor (señal de deuda conocida, no resuelta).

Veredicto due-diligence: **adquirible como MVP / prueba de concepto, NO como plataforma de producción confiable**. Las cifras que muestra el dashboard ejecutivo no son confiables en este momento (double counting de transacciones, "Items Sold" mal calculado, datos diarios del API sin dimensión de producto). Ninguno es irreparable, pero hasta corregirlos **no se debe tomar decisión de negocio con este dashboard**.

El riesgo más grave no es arquitectónico — es **silencioso**: el sistema pierde y duplica datos sin fallar ni alertar. Un comprador hereda métricas con apariencia de precisión y cero observabilidad para detectar cuándo mienten.

Madurez global: **4.7 / 10** (detalle en scorecard).

---

## 2. Hallazgos críticos

### C1 — `order_count` no es aditivo → double counting en KPIs
`fact_sales` tiene grano `día×tienda×producto×canal` y calcula `count(distinct order_id)` **por grano**. El dashboard luego hace `sum(f.order_count)` (`index.md:24`). Una orden con 3 productos en 2 canales cuenta múltiples veces.
- **Impacto:** "Items Sold", "Avg Ticket" (current month y YTD), leaderboards — todos inflados. Net Sales sí es correcto (aditivo); el ratio avg_ticket queda subestimado porque el denominador está inflado.
- **Fix:** separar conteo de transacciones a un grano `día×tienda×orden` (o tabla `fact_orders` distinta de `fact_sale_items`). No sumar `count(distinct)` a través de grano. Prioridad **P0**.

### C2 — "Items Sold" no cuenta ítems; LS2 usa `Account` como `order_id`
La KPI etiquetada "Items Sold" muestra `order_count` (órdenes distintas), no ítems vendidos — e ignora la columna `Qty` que existe en LS2. Peor: en `stg_ls2.sql` `order_id = "Account"` (número de cuenta/check, no orden). `count(distinct order_id)` cuenta cuentas, no transacciones ni ítems.
- **Impacto:** métrica de volumen doblemente errónea y mal etiquetada. Inconsistente entre PAR (Order ID real) y LS2 (Account).
- **Fix:** "Items Sold" = `sum(Qty)`; definir clave de orden real en LS2 o documentar que no existe. **P0**.

### C3 — Datos diarios del API no tienen dimensión de producto ni categoría
En `par_api.py` → `build_raw_par2_rows`: `Item Name = None`, `Discount Total = None`, y `Revenue Center = DayPartId` (el propio comentario admite que `RevenueCenterId` no se expone). Como `fact_sales` une producto por `Item Name`, **toda la data del API cae en `product_key = 0 (UNKNOWN)`** y la categoría Beverage/Food/Retail queda mal mapeada (DayPart ≠ Revenue Center).
- **Impacto:** el API es el driver **diario** (lo único que corre en CI). Items Analysis, Category Mix, Attachment Rate, Menu Optimization → vacíos o basura para todo dato reciente. El dashboard solo tiene producto correcto para meses con CSV cargado manualmente.
- **Fix:** mapear `ItemName`/`RevenueCenter` reales desde el API (probablemente requiere `GetMenu`/catálogo PAR), o aceptar explícitamente que producto solo existe vía CSV y ocultar esas vistas para fechas API. **P0 conceptual.**

### C4 — Dos escritores sobre `bronze.raw_par2` con semánticas de borrado incompatibles
El loader CSV hace `DELETE FROM raw_par2 WHERE Date BETWEEN min AND max` (rango del archivo, **todas las tiendas**). El API hace `DELETE WHERE Location=:s AND Date=:d`. Cargar el CSV de un mes **borra las filas del API de ese mes** para todas las tiendas antes de re-append (y el CSV no trae el detalle de producto del API). Y viceversa el API solo pisa su tienda/día.
- **Impacto:** clobbering silencioso entre fuentes en la misma tabla. Pérdida de datos sin error.
- **Fix:** separar tablas por fuente (`raw_par2_csv` vs `raw_par2_api`) o `DELETE` con predicado `_source_system`. **P0.**

### C5 — Watermark incremental por `sale_date` descarta datos tardíos/backfill en silencio
`stg_par2`/`stg_ls2` son `incremental_strategy='append'` con filtro `sale_date > max(sale_date)`. `fact_sales` igual. Si bronze se re-borra/re-carga para fechas pasadas (reload de CSV), silver **no las re-lee** (watermark ya pasó) → bronze y silver divergen. El propio `Makefile`/README exige `--full-refresh` manual como workaround.
- **Impacto:** corrección depende de que un humano recuerde `make migrate-csv` con `--full-refresh`. Cualquier dato que llegue tarde o se corrija aguas arriba se pierde silenciosamente.
- **Fix:** estrategia incremental real — `incremental_strategy='delete+insert'`/`merge` con `unique_key` por grano, ventana de re-proceso (ej. últimos N días siempre re-computados). **P0.**

### C6 — TLS verification deshabilitado en el cliente PAR
`httpx.AsyncClient(verify=False)` enviando `AccessToken` y `LocationToken` en headers.
- **Impacto:** credenciales POS expuestas a MITM. Inaceptable en producción.
- **Fix:** `verify=True` + CA bundle correcto; si el endpoint tiene cert roto, pinear cert específico, nunca desactivar global. **P0 seguridad.**

### C7 — Password de BD en texto plano commiteado (detectado en esta sesión)
`dashboard/sources/gold/connection.yaml` tenía host+user+password reales de Supabase reemplazando los `${SUPABASE_*}`. Quedó fuera del commit, pero **si alguna vez se pusheó, está en el historial de git**.
- **Fix:** `git log -p -- dashboard/sources/gold/connection.yaml` para verificar; si apareció, **rotar credencial Supabase ya** y purgar historial. **P0 seguridad.**

---

## 3. Hallazgos importantes

### H1 — `tip_amount` hardcodeado a `0.0` en PAR y LS2
`stg_par2`/`stg_ls2`: `0.0 as tip_amount`. El API sí parsea `TipAmount` pero no llega a `fact_sales` (se pierde en el mapeo a producto). La página entera **"Tip Performance Index"** (`operations.md`) mide siempre 0.
- **Fix:** propagar tip real; ocultar la métrica hasta entonces. **P1.**

### H2 — Surrogate keys vía `abs(hashtext(...))`, sin SCD
`store_key`/`product_key`/`employee_key` = hash del nombre. `hashtext` es 32-bit, no determinista entre versiones de Postgres, con riesgo de colisión a escala de miles de productos, y **acopla la clave al texto** — un rename de tienda/producto crea una llave nueva y rompe historia. No hay SCD Type 2 en ninguna dimensión.
- **Fix:** SK secuenciales/`dbt_utils.generate_surrogate_key` con seed estable + tabla de mapeo natural-key→SK persistida; SCD2 donde haya atributos cambiantes (royalty, categoría). **P1.**

### H3 — Reglas de negocio hardcodeadas (`royalty_rate`)
`dim_store`: `CASE WHEN store_name LIKE 'MEIJER%' THEN 0.04 ...` con default 0.07 silencioso. Tienda nueva → royalty incorrecto sin aviso.
- **Fix:** dbt seed `store_royalties.csv` versionado/gobernado, join explícito, test `not_null` sobre el rate. **P1.**

### H4 — CSV ingestion está muerta en CI
`data/` está en `.gitignore` → el checkout de CI no tiene CSVs → el step "Load new data" siempre cae en "skipping". En la práctica **solo el API corre automático**; los CSV son 100% proceso manual local. Documentado, pero es fragilidad operativa grave: la historia mensual depende de que una persona corra comandos a mano sin errar el `--full-refresh`.
- **Fix:** subir CSVs a object storage (R2/S3) e ingerir desde ahí en CI, o un workflow dedicado de backfill con upload. **P1.**

### H5 — Sin retries/backoff/rate-limit en el API; un fallo tumba todo el pipeline
`process_store` captura excepción por tienda pero `run()` hace `sys.exit(1)` si **cualquiera** falla → job CI rojo → **no deploy**. Una tienda con timeout bloquea el dashboard de todas. Llamadas secuenciales (`await` en loop, no `gather`) → latencia O(tiendas).
- **Fix:** retries con backoff exponencial (tenacity), aislar fallo por tienda (deploy parcial + alerta), `asyncio.gather` con límite de concurrencia. **P1.**

### H6 — Testing dbt mínimo; sin uniqueness/relationship/freshness
`schema.yml` solo tiene `not_null` + `is_non_negative`. **No hay test de unicidad sobre el grano de los facts**, ni `relationships` FK→dim, ni `dbt source freshness`. Los 333 tests Python cubren parsing/ingesta/CI (bien), pero **la corrección semántica del modelo no se testea** — por eso C1–C5 pasan verdes.
- **Fix:** `unique` sobre `unique_key` de cada fact, `relationships` a cada dim, freshness sources, tests de reconciliación. **P1.**

### H7 — Sin staging/rollback/DR
`dbt run` corre directo contra el schema de producción; deploy directo a Pages prod. Sin entorno de staging, sin blue/green, sin snapshot/backup explícito de Supabase, sin rollback del dashboard.
- **Fix:** target dbt `staging` + swap, retención de backups Supabase verificada, deploy con preview environment. **P1.**

---

## 4. Hallazgos menores

- **M1** `datetime.utcnow()` deprecado y naive (`csv.py`, `par_api.py`) → usar `datetime.now(UTC)`.
- **M2** Comparaciones YoY hardcodeadas ("May 2026 vs May 2025" en specs) → rotan; parametrizar por `current_date`.
- **M3** KPI "current month" se rompe si el API va atrasado (mes en curso vacío) — sin fallback ni indicador de freshness en la card.
- **M4** Heurísticas regex de `product_canonical_name` divergen entre PAR y LS2 → mismo producto, canónico distinto → mezcla de mix.
- **M5** R2 offload + patch de WASM (`ci/r2_offload.py`) es un hack frágil para servir Evidence en Cloudflare; se rompe con upgrades de Evidence.
- **M6** Joins de fact por string `product_name` en vez de SK numérica → frágil a espacios/acentos y más lento.
- **M7** Sin documentación dbt (`description:` ausente), sin `exposures`, sin catálogo/lineage.
- **M8** Páginas duplicadas/legacy en dashboard (`forecast` vs `forecasting`, `products`, `trends`, `performance`) → riesgo de métricas divergentes entre páginas.
- **M9** `_source_system` se trackea pero no hay test de reconciliación CSV vs API que use la página `data_quality` prometida.

---

## 5. Evaluación por dominio

**Arquitectura.** Separación de capas correcta (ingesta / dbt / BI). Acoplamiento problemático: API y CSV comparten tabla bronze (C4); reglas de negocio embebidas en SQL (H3). Resiliencia baja (H5, H7). Evolutividad media — el patrón class-based de ingesta es extensible y limpio.

**Data Platform.** Medallion correcto conceptualmente. La estrategia incremental es el talón de Aquiles: `append`+watermark sin merge produce los riesgos de pérdida/inconsistencia C5. Idempotencia solo a nivel archivo (watermark), no a nivel registro. Backfill = comando manual frágil.

**Modelado dimensional.** Star schema razonable. Grano de fact mezcla ítems y órdenes generando C1. SK por hashtext (H2), cero SCD, royalty hardcodeada. `dim_product` con 4 categorías fijas y lógica de prioridad PAR>LS2 bien pensada — el mejor modelo del repo. No soportará multi-marca/multi-país sin rediseño (no hay `dim_brand`, `dim_country`, `dim_currency`; net_sales asume una moneda).

**dbt.** Estructura por dominio limpia, `ref()` correcto, materializations apropiadas. Falla en testing (H6), documentación (M7) y estrategia incremental (C5). No usa `dbt_utils`, `snapshots`, ni `exposures`.

**Calidad de datos.** Casi inexistente como disciplina: no hay freshness, reconciliation, volume ni anomaly checks. Los `UNKNOWN`/`destination_key=0` se generan pero no se monitorean. La página `data_quality` es UI sin motor de control real.

**Testing.** Fuerte en unit/ingesta (parsing, watermark, loader, workflow). Débil/ausente en: corrección semántica del modelo, integración end-to-end, contract tests del API, regresión de métricas. Cobertura alta = ingesta; media = lógica SQL aislada; baja = correctitud de negocio.

**Dashboard.** Evidence usado correctamente en lo técnico (queries en build → parquet estático, buena performance runtime). Pero la capa semántica no está centralizada → cada página redefine métricas → riesgo de divergencia (M8). Métricas afectadas por C1/C2/H1 no son confiables. Falta: cohortes, retención, márgenes reales, P&L por tienda.

**CI/CD.** Declarativo y legible. SPOF: cualquier fallo de tienda mata el deploy (H5); sin staging/rollback (H7); CSV ingestion inerte (H4); generación de `profiles.yml`/`connection.yaml` inline con secretos parseados en cada run (funciona, pero secreto pasa por env en texto).

**Seguridad.** Crítico: TLS off (C6), password commiteado (C7). Secrets en GitHub Secrets (correcto). Sin gestión de privilegios mínimos (dbt usa el mismo super-user Postgres para todo), sin auditoría de accesos, `rejectUnauthorized:false` también en Evidence.

**Observabilidad.** `print()` a stdout, nada más. Sin logging estructurado, sin métricas, sin alertas, sin lineage, sin SLA/SLO. Cero capacidad de saber cuándo los datos están mal.

---

## 6. Costos y escalabilidad

Evidence ejecuta SQL en **build-time** → dashboard estático → costo runtime ~0 (bien). La carga real cae sobre Supabase en cada build dbt + sources.

| Escala | Cuello probable |
|---|---|
| 10 tiendas | Ninguno técnico. El proceso **manual de CSV** ya duele. |
| 50 tiendas | Ingesta API secuencial (H5) → ventana de pipeline crece linealmente; build dbt sobre fact creciente en single-node Postgres empieza a notarse. |
| 100 tiendas | Supabase single-node para agregaciones full-refresh; proceso CSV manual colapsa; rate limits PAR. |
| 500 tiendas | Postgres OLAP insuficiente → migrar fact a motor columnar (DuckDB/MotherDuck, ClickHouse, BigQuery). Ingesta debe ser paralela + orquestada (Airflow/Dagster). |

**Primer cuello real (no técnico): el proceso operativo manual de CSV.** Llega antes que cualquier límite de cómputo, probablemente a ~10–15 tiendas.

---

## 7. Technical Debt Assessment

| # | Issue | Impacto | Prob. | Severidad | Esfuerzo | Prioridad |
|---|---|---|---|---|---|---|
| C1 | order_count no aditivo (double counting) | Alto | Seguro (activo) | Crítica | M | P0 |
| C2 | "Items Sold" mal calculado / order_id=Account LS2 | Alto | Seguro | Crítica | M | P0 |
| C3 | API sin producto/categoría | Alto | Seguro | Crítica | L | P0 |
| C4 | Dos escritores sobre raw_par2 | Alto | Media-Alta | Crítica | S | P0 |
| C5 | Watermark descarta data tardía | Alto | Media | Crítica | M | P0 |
| C6 | TLS verify=False | Alto | Baja | Crítica | XS | P0 |
| C7 | Password commiteado | Crítico | — (ocurrido) | Crítica | S | P0 |
| H1 | tip_amount=0 hardcodeado | Medio | Seguro | Alta | S | P1 |
| H2 | SK por hashtext, sin SCD | Medio | Media | Alta | L | P1 |
| H3 | royalty hardcodeada | Medio | Alta | Alta | S | P1 |
| H4 | CSV ingestion muerta en CI | Alto | Seguro | Alta | M | P1 |
| H5 | Sin retries; 1 fallo tumba deploy | Alto | Media | Alta | M | P1 |
| H6 | Testing dbt mínimo | Alto | Seguro | Alta | M | P1 |
| H7 | Sin staging/rollback/DR | Alto | Baja | Alta | L | P1 |
| M1 | utcnow deprecado | Bajo | Seguro | Baja | XS | P2 |
| M2 | YoY hardcodeado | Bajo | Alta | Media | XS | P2 |
| M3 | KPI mes en curso sin freshness | Medio | Alta | Media | S | P2 |
| M4 | canonical regex divergente | Medio | Media | Media | S | P2 |
| M5 | R2/WASM hack frágil | Medio | Media | Media | M | P2 |
| M6 | join por string | Bajo | Media | Baja | M | P3 |
| M7 | sin docs/lineage dbt | Medio | Seguro | Media | M | P2 |
| M8 | páginas legacy duplicadas | Medio | Alta | Media | S | P2 |
| M9 | sin reconciliación real | Medio | Seguro | Media | M | P2 |

---

## 8. Roadmap priorizado

### 30 días — parar el sangrado (corrección + seguridad)
- C6 `verify=True`; C7 verificar historial git + rotar credencial Supabase (hoy).
- C4 separar tablas/predicado por `_source_system`.
- C1/C2 rediseñar grano: `fact_order` (transacciones) separado de `fact_sale_item` (ítems con Qty). Corregir KPIs.
- H1 desactivar página de tips hasta tener dato real.
- H6-mínimo: añadir `unique` sobre grano de facts + `relationships` a dims (atrapa regresiones futuras).
- Banner de freshness real en el dashboard (saber cuándo los datos mienten).

### 90 días — estructura
- C5 incremental real (`delete+insert`/`merge` + ventana de reproceso N días).
- C3 traer producto/revenue-center reales del API (o aislar formalmente vistas que dependen de producto).
- H2 SK estables + SCD2 en dim_store/dim_product.
- H3 royalty como seed gobernado.
- H4 CSVs en object storage, ingesta en CI.
- H5 retries + aislamiento por tienda + deploy parcial.
- Data quality framework: freshness, volume, reconciliation CSV↔API, anomaly. Alertas (Slack/email) ante fallo.
- Capa de métricas centralizada (dbt metrics / semantic layer) para matar M8.

### 12 meses — arquitectura objetivo
- Orquestador (Dagster/Airflow) con lineage y reintentos nativos.
- Motor columnar para fact (MotherDuck/ClickHouse/BigQuery) si >50 tiendas.
- Modelo multi-marca/país/moneda (`dim_brand`, `dim_country`, `dim_currency`).
- Staging environment + CI con preview + rollback.
- Observabilidad: logging estructurado, métricas de pipeline, SLO de freshness, dashboard de salud de datos.
- Contract testing contra PAR API.

---

## 9. Scorecard final

| Dimensión | Nota | Justificación |
|---|---|---|
| Arquitectura | **6/10** | Capas y patrones limpios; acoplamiento bronze compartido y reglas en SQL restan. |
| Ingeniería de datos | **5/10** | Ingesta class-based sólida; incremental frágil, sin retries, CSV manual. |
| Modelado | **4/10** | Star schema correcto pero grano roto (C1), SK por hash, cero SCD, mono-moneda. |
| Calidad de datos | **2/10** | Casi inexistente; sin freshness/reconciliation/anomaly; UNKNOWN sin monitoreo. |
| Testing | **5/10** | Fuerte en unit/ingesta; nula cobertura de corrección semántica (deja pasar C1–C5). |
| Operaciones | **4/10** | CI legible pero CSV manual, SPOF en deploy, sin runbook real. |
| Observabilidad | **2/10** | Solo `print()`; sin logging/alertas/lineage/SLO. |
| Seguridad | **2/10** | TLS off + password commiteado + super-user único. Fallos graves y básicos. |
| Escalabilidad | **5/10** | Build estático ayuda; ingesta secuencial y proceso manual limitan a ~10–50 tiendas. |
| Mantenibilidad | **6/10** | Código Python limpio y tipado, dbt ordenado; falta docs, hay páginas duplicadas. |

**Global ponderado: 4.7 / 10.**

**Recomendación de adquisición:** comprar solo con descuento que refleje 30–90 días de remediación P0/P1, y **congelar el uso del dashboard para decisiones de negocio hasta cerrar C1–C5**. El activo de valor es el código de ingesta y la estructura dbt; la capa de métricas y la corrección de datos requieren reconstrucción dirigida, no parches.
