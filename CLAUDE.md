# Context & Global Rules for Claude Code
You are an expert data engineer and frontend developer specializing in Evidence.dev. You will implement and upgrade a multi-page dashboard. 

## Strict Global Constraints:
1. **Language:** ALL titles, KPIs, labels, charts, table headers, and metrics displayed anywhere on the dashboard MUST be in **English**.
2. **Framework:** Use Evidence.dev syntax (Markdown + SQL blocks + Evidence components like `<Value />`, `<DataTable />`, `<BarChart />`, `<LineChart />`, etc.).
3. **Database Engine:** Assume backend is running DuckDB. Use standard DuckDB SQL syntax for dates, rollups, and aggregations.
4. **Scoping & Filters:** Implement dynamic inputs (`<Select />`, `<DateRange />`) as specified. Ensure queries react correctly to these reference variables.

---

# Implementation Plan & Specifications

## 1. Home / Executive Overview (`index.md`)

### Top Metric Row (KPI Cards)
Implement visual KPI cards using `<Value />` components. Filterable by a store selection dropdown (`${inputs.store_filter}`).
* **Net Sales (Current Month):** SUM of net sales for the ongoing calendar month.
* **Net Sales (YTD):** SUM of net sales from January 1st of the current year to the maximum available date in the dataset.
* **Average Ticket (Current Month):** Net sales divided by order count for the current month.
* **Average Ticket (YTD):** Net sales divided by order count YTD.
* **Sales Volume (Current Month):** Total count of items sold / transactions for the current month.
* **Sales Volume (YTD):** Total count of items sold / transactions YTD.

### Time Series Chart
* **Component:** `<LineChart />` or `<AreaChart />`
* **Data:** Daily aggregated Total Net Sales for the **last 90 days**.
* **Interactivity:** Must react to the store selection filter.

### Store Leaderboard
* **Component:** `<DataTable />`
* **Metrics:** Rank stores by Month-over-Month (MoM) percentage growth.
* **Calculation:** Compare Net Sales of the current month vs. previous month per store. Formula: `((Current_Month - Prev_Month) / Prev_Month) * 100`.

### Operational Performance Tables
* **Labor Efficiency Score Table:** Display a list of stores/employees using `fact_sales_by_employee`. Calculate the ratio: `Net Sales / Active Employee Count`.
* **Estimated Royalties Table:** Calculate dynamic franchise fees accrued during the current month. The royalty rate must vary dynamically based on the specific store rules (use a `CASE WHEN` statement or join a mapping table if available).

---

## 2. Items Analysis (`items_analysis.md`)
*Global Filters for this page: Store Filter (`${inputs.store}`) and Date Range Filter (`${inputs.date_range}`).*

### Overall Performance Table
* **Component:** `<DataTable />` with search and pagination.
* **Columns:** `Store Name`, `Net Sales`, `Items Sold`.

### Size Breakdown Analysis
* **Component:** Include a dropdown filter (`<Select />`) to switch between sizes: `12oz`, `16oz`, `20oz`, `24oz`, `32oz`, `Food`.
* **Table Columns:** * `Net Sales`
    * `Items Sold`
    * `% of Sales` -> Calculate the financial percentage contribution of each specific product within the selected size context relative to the total sales of that specific size group: `($ Product Net Sales / $ Total Size Net Sales) * 100`.

---

## 3. Store Performance Breakdown (`/stores/[store_id].md` or dynamic parameter page)
*Crucial: This analysis must be fully isolated and individualized per store using Evidence parameterized routing.*

### Store Specific KPIs
* Top row cards for the specific store: `Average Ticket`, `Net Sales (Current Month)`, and `Net Sales (YTD)`.

### Sales Heatmap (Hours vs. Days)
* **Component:** Heatmap or matrix visual.
* **X-Axis:** Hour of the day (0-23). **Y-Axis:** Day of the week (Monday-Sunday).
* **Value:** Transaction count or Net Sales to identify peak traffic hours for scheduling optimization.

### Category Mix
* **Component:** `<DonutChart />` or `<PieChart />`
* **Data:** Percentage breakdown of `Beverage` vs `Food` net sales. (Goal: Monitor and push food attachment rate).

### Trend Line (L-7D)
* **Component:** `<LineChart />`
* **Data:** Net Sales over the last 7 days.
* **Feature:** Overlay a moving average trendline band to smooth out daily variance.

### Top Channels by Store
* **Component:** Comparative chart showing distribution channel performance.
* **Insight:** Clearly contrast `Drive-Thru` volume/sales versus `Delivery` volume/sales for this specific location.

---

## 4. Channels & Destinations Analysis (`channels.md`)
*Focus: Strategic mapping of customer acquisition vectors and servicing costs using `dim_destination`.*

### Channel Comparison
* **Component:** `<BarChart />` (grouped or multi-axis).
* **Metrics:** Compare `Net Sales` and `Average Ticket` across all operational channels.
* **Business Goal:** Evaluate if the operational overhead of `Catering` is justified by a significantly higher average ticket compared to `In-Store`.

### Delivery Leakage
* **Component:** Visual comparison chart or stacked bar.
* **Metrics:** Map `Net Sales` directly against `Discount Total` specifically for 3rd-party delivery channels to expose margin erosion from promotions.

### Drive-Thru Tracking
* **Component:** Hourly volume chart.
* **Metric:** Hourly volume throughput for Drive-Thru lanes (and prepare the structure to ingest response/service times from the PAR API once available).

---

## 5. Labor & Operations Strategy (`operations.md`)
*Leveraging data from `dim_employee` and `fact_sales_by_employee`.*

### Up-selling Leaderboard
* **Component:** `<DataTable />` ranking baristas.
* **Metric:** Highest `Average Ticket` per employee. Identifies team members successfully suggesting modifiers, size upgrades, or food items.

### Tip Performance Index
* **Component:** Ranked chart or table.
* **Metric Ratio:** `Tip Amount / Net Sales` per employee. Used as a proxy metric for customer service quality.

### Shift Productivity
* **Component:** Table or bar chart.
* **Metric:** Orders processed per employee per hour.

### Discount Audit Trail
* **Component:** Risk mitigation `<DataTable />`.
* **Metric:** Ranked list of employees by total absolute volume of `Discount Total` issued. Designed to spot potential fraud, internal theft, or systemic abuse of complimentary items.

---

## 6. Revenue Centers & Menu Optimization (`menu.md`)
*Utilizing `dim_product` and transactional tables.*

### Attachment Rate
* **Component:** KPI metric and historical line chart.
* **Metric:** Percentage of unique transactions containing at least one `Beverage` item that also include at least one `Food` item. *Note: You must evaluate this by performing a self-join or subquery grouping at the `order_id` level.*

### Product Mix Evolution
* **Component:** Stacked area chart or multi-line chart.
* **Data:** Track sales volume and revenue changes for the `Retail` category (e.g., coffee beans, mugs, merchandise) over time, starting from **July 2024** to the present.

### Estimated Waste Analysis (Placeholder Structure)
* Create a clean UI section mapping the relationship between `Net Sales` and theoretical inventory depletion, leaving hooks for a future inventory system integration.

---

## 7. Predictive Analytics & Forecasting (`forecasting.md`)

### Sales Forecasting
* **Component:** `<LineChart />` with distinct styling for actual vs. predicted values.
* **Logic:** Generate a predictive projection of total sales for the remainder of the current month. Base the baseline run-rate on historical trends since **2024** using DuckDB time-series capabilities or linear regression functions.

### Year-over-Year (YoY) Comparison
* **Component:** Split comparison cards or a delta chart.
* **Logic:** Compare **May 2026** performance directly against **May 2025** across Net Sales and transaction volume to diagnose macro brand growth.

### Weekday Profiling
* **Component:** Grouped bar chart.
* **Logic:** Compare product category sales mix behavior on **Mondays** (expecting caffeine-heavy spikes) versus **Sundays** (expecting higher retail and food attach rates).

---

## 8. Data Quality & Reconciliation Control (`data_quality.md`)
*Cross-referencing ingestion inputs from PAR API, PAR CSV, and LS2.*

### Source Reconciliation
* **Component:** Side-by-side `<BarChart />`.
* **Logic:** Aggregate and compare total revenue grouped by `_source_system`. Track discrepancies between CSV payloads and API extractions.

### Unknown Tracker
* **Component:** Alert panel / Counter metric.
* **Logic:** Count instances where `dim_employee` exhibits `UNKNOWN` strings or where `destination_key = 0`. An increasing delta indicates an upstream ingestion pipeline fracture.

### Freshness Monitor
* **Component:** Clean banner or badge.
* **Logic:** Display the exact timestamp of the latest successful data load (Data Watermark).