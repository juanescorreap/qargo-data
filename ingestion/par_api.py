"""
PAR POS (Brink) Sales2.svc — ingestion pipeline for Qargo Coffee.

Usage:
    python ingestion/par_api.py                           # all stores, yesterday
    python ingestion/par_api.py --date 2026-05-27         # all stores, specific date
    python ingestion/par_api.py --date 2026-05-27 --store SANDBOX
    python ingestion/par_api.py --date 2026-05-27 --dry-run

Env vars (~/qargo-data/.env):
    PAR_ACCESS_TOKEN            global auth token
    PAR_SANDBOX_LOCATION_TOKEN  sandbox location token
    PAR_SANDBOX_URL             sandbox endpoint URL
    PAR_LOCATION_TOKEN_{NAME}   per-store production token (e.g. PAR_LOCATION_TOKEN_TAMPA)
    PAR_ENDPOINT_{NAME}         per-store endpoint override (falls back to PAR_DEFAULT_ENDPOINT)
    PAR_DEFAULT_ENDPOINT        default production endpoint
    SUPABASE_DB_URL             PostgreSQL connection string
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).parents[1] / ".env")

SOAP_NS = "http://www.brinksoftware.com/webservices/sales/v2"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


# ── SOAP client ────────────────────────────────────────────────────────────────

class PARSoapClient:
    def __init__(self, endpoint: str, access_token: str, location_token: str) -> None:
        self.endpoint = endpoint
        self.access_token = access_token
        self.location_token = location_token

    def _envelope(self, body: str) -> str:
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"'
            f' xmlns:v2="{SOAP_NS}">'
            "<soapenv:Header/>"
            f"<soapenv:Body>{body}</soapenv:Body>"
            "</soapenv:Envelope>"
        )

    def _headers(self, action: str) -> dict[str, str]:
        return {
            "Content-Type": "text/xml;charset=UTF-8",
            "SOAPAction": f'"{SOAP_NS}/ISalesWebService2/{action}"',
            "AccessToken": self.access_token,
            "LocationToken": self.location_token,
            "Connection": "Keep-Alive",
        }

    async def _call(self, action: str, body: str) -> ET.Element:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                self.endpoint,
                content=self._envelope(body),
                headers=self._headers(action),
                timeout=60.0,
            )
        if resp.status_code != 200:
            print(f"[PAR] ERROR status={resp.status_code}", file=sys.stderr)
            print(f"[PAR] body={resp.text}", file=sys.stderr)
            resp.raise_for_status()
        root = ET.fromstring(resp.text)
        soap_body = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Body")
        if soap_body is None or not list(soap_body):
            raise ValueError(f"Empty SOAP body in response: {resp.text[:500]}")
        return list(soap_body)[0]

    async def get_business_date(self) -> dict[str, Any]:
        el = await self._call("GetCurrentBusinessDate", "<v2:GetCurrentBusinessDate/>")
        return _unwrap(_xml_to_dict(el))  # type: ignore[return-value]

    async def get_orders(
        self,
        business_date: str,
        exclude_open: bool = True,
        price_rollup: str = "RollUp",
    ) -> dict[str, Any]:
        body = (
            "<v2:GetOrders>"
            "<v2:request>"
            f"<v2:BusinessDate>{business_date}</v2:BusinessDate>"
            f"<v2:ExcludeOpenOrders>{'true' if exclude_open else 'false'}</v2:ExcludeOpenOrders>"
            f"<v2:PriceRollUp>{price_rollup}</v2:PriceRollUp>"
            "</v2:request>"
            "</v2:GetOrders>"
        )
        el = await self._call("GetOrders", body)
        return _unwrap(_xml_to_dict(el))  # type: ignore[return-value]


# ── XML helpers ────────────────────────────────────────────────────────────────

def _xml_to_dict(element: ET.Element) -> dict[str, Any] | str | None:
    if element.attrib.get(f"{{{XSI_NS}}}nil") == "true":
        return None
    children = list(element)
    if not children:
        return element.text
    result: dict[str, Any] = {}
    for child in children:
        tag = child.tag.split("}")[-1]
        value = _xml_to_dict(child)
        if tag in result:
            if not isinstance(result[tag], list):
                result[tag] = [result[tag]]
            result[tag].append(value)
        else:
            result[tag] = value
    return result


def _unwrap(data: dict[str, Any] | str | None) -> dict[str, Any] | str | None:
    """Peel one wrapper layer off a single-key dict (e.g. GetOrdersResult → its contents)."""
    if not isinstance(data, dict):
        return data
    for value in data.values():
        if isinstance(value, dict):
            return value
    return data


# ── Store config ───────────────────────────────────────────────────────────────

@dataclass
class StoreConfig:
    store_name: str
    location_token: str
    endpoint: str


def load_store_configs() -> list[StoreConfig]:
    configs: list[StoreConfig] = []
    default_endpoint = os.getenv("PAR_DEFAULT_ENDPOINT", "")

    sandbox_token = os.getenv("PAR_SANDBOX_LOCATION_TOKEN")
    sandbox_url = os.getenv("PAR_SANDBOX_URL")
    if sandbox_token and sandbox_url:
        configs.append(StoreConfig("SANDBOX", sandbox_token, sandbox_url))

    for key, val in os.environ.items():
        if not key.startswith("PAR_LOCATION_TOKEN_"):
            continue
        suffix = key[len("PAR_LOCATION_TOKEN_"):]
        if suffix == "SANDBOX":
            continue  # handled above
        endpoint = os.getenv(f"PAR_ENDPOINT_{suffix}", default_endpoint)
        if not endpoint:
            print(f"[config] WARN: no endpoint for store {suffix}, skipping", file=sys.stderr)
            continue
        configs.append(StoreConfig(suffix, val, endpoint))

    return configs


# ── Order / entry parsing ──────────────────────────────────────────────────────

def _get(d: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, default)
    return d


def _float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _bool(val: Any) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    return str(val).lower() == "true"


def _to_list(val: Any) -> list[Any]:
    """Wrap a single dict/value in a list; pass lists through; return [] for None."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def parse_orders(
    raw: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse a GetOrders response dict into (order_rows, entry_rows).

    The PAR XML uses 'Id'/'Number' at the order level and nests entries
    under 'Entries.OrderEntry', as confirmed by the zeep-based reference client.
    """
    orders: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []

    if not isinstance(raw, dict):
        return orders, entries

    result_code = _get(raw, "ResultCode")
    if result_code is not None and str(result_code) != "0":
        raise ValueError(f"PAR API ResultCode={result_code}: {_get(raw, 'Message')}")

    # Orders.Order is a single dict when 1 order, a list when multiple
    order_items = _to_list(_get(raw, "Orders", "Order"))

    for order in order_items:
        if not isinstance(order, dict):
            continue
        order_id = _get(order, "Id")  # zeep confirms field is 'Id'
        orders.append({
            "order_id": order_id,
            "order_number": _get(order, "Number"),
            "is_closed": _bool(_get(order, "IsClosed")),
            "is_refund": _bool(_get(order, "IsRefund")),
            "is_voided": _bool(_get(order, "IsVoided")),
            "net_sales": _float(_get(order, "NetSales")),
            "gross_sales": _float(_get(order, "GrossSales")),
            "total": _float(_get(order, "Total")),
            "subtotal": _float(_get(order, "SubTotal")),
            "tax": _float(_get(order, "Tax")),
            "guest_count": _get(order, "GuestCount"),
            "tip_amount": _float(_get(order, "TipAmount")),
            "opened_time": _get(order, "OpenedTime"),
            "closed_time": _get(order, "ClosedTime"),
            "terminal_id": _get(order, "TerminalId"),
            "till_number": _get(order, "TillNumber"),
            "employee_id": _get(order, "EmployeeId"),
            "destination_id": _get(order, "DestinationId"),
        })

        # Entries.OrderEntry is a single dict when 1 entry, a list when multiple
        entry_items = _to_list(_get(order, "Entries", "OrderEntry"))
        for entry in entry_items:
            if not isinstance(entry, dict):
                continue
            entries.append({
                "order_id": order_id,
                "entry_id": _get(entry, "Id"),
                "item_id": _get(entry, "ItemId"),
                # PAR uses DayPartId at the entry level; RevenueCenterId is not exposed here
                "revenue_center_id": _get(entry, "DayPartId"),
                "net_sales": _float(_get(entry, "ItemNetSales")),
                "gross_sales": _float(_get(entry, "ItemGrossSales")),
                "display_price": _float(_get(entry, "DisplayPrice")),
                "is_voided": _bool(_get(entry, "IsVoided")),
                "is_deleted": _bool(_get(entry, "IsDeleted")),
            })

    return orders, entries


def build_raw_par2_rows(
    orders: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    store_name: str,
    business_date: str,
) -> list[dict[str, Any]]:
    """Map parsed entry-level data to the bronze.raw_par2 column schema."""
    order_map = {o["order_id"]: o for o in orders}
    ingested_at = pd.Timestamp.now("UTC")
    rows = []
    for entry in entries:
        order = order_map.get(entry["order_id"], {})
        rows.append({
            "Location": store_name,
            "Date": business_date,
            "Employee Name": order.get("employee_id"),
            "Item ID": entry.get("item_id"),
            "Item Name": None,
            "Item PLU": None,
            "Price": entry.get("display_price"),
            "Discount Total": None,
            "Promotion Total": None,
            "Taxes": order.get("tax"),
            "Net Sales": entry.get("net_sales"),
            "Gross Sales": entry.get("gross_sales"),
            "Total Sales": entry.get("gross_sales"),
            "Revenue Center": entry.get("revenue_center_id"),
            "Has Employee Discount": None,
            "Destination": order.get("destination_id"),
            "Voided": entry.get("is_voided"),
            "Has Customer": None,
            "Is Modifier": None,
            "Order ID": entry["order_id"],
            "_source_file": None,
            "_source_system": "par_api",
            "_ingested_at": ingested_at,
        })
    return rows


# ── DB writer ──────────────────────────────────────────────────────────────────

_RAW_PAR2_ENTRIES_DDL = """
CREATE TABLE IF NOT EXISTS bronze.raw_par2_entries (
    order_id          TEXT          NOT NULL,
    entry_id          TEXT          NOT NULL,
    item_id           TEXT,
    revenue_center_id TEXT,
    net_sales         DOUBLE PRECISION,
    gross_sales       DOUBLE PRECISION,
    display_price     DOUBLE PRECISION,
    is_voided         BOOLEAN,
    is_deleted        BOOLEAN,
    store_name        TEXT,
    business_date     DATE,
    _ingested_at      TIMESTAMP,
    PRIMARY KEY (order_id, entry_id)
);
"""


def write_raw_par2(
    engine: Any,
    rows: list[dict[str, Any]],
    store_name: str,
    business_date: str,
) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    with engine.begin() as conn:
        conn.execute(
            text('DELETE FROM bronze.raw_par2 WHERE "Location" = :s AND "Date" = :d'),
            {"s": store_name, "d": business_date},
        )
        df.to_sql("raw_par2", conn, schema="bronze", if_exists="append", index=False)
    return len(df)


def write_entries(
    engine: Any,
    entries: list[dict[str, Any]],
    store_name: str,
    business_date: str,
) -> int:
    if not entries:
        return 0
    ingested_at = pd.Timestamp.now("UTC")
    df = pd.DataFrame([
        {**e, "store_name": store_name, "business_date": business_date, "_ingested_at": ingested_at}
        for e in entries
    ])
    with engine.begin() as conn:
        conn.execute(text(_RAW_PAR2_ENTRIES_DDL))
        conn.execute(
            text(
                "DELETE FROM bronze.raw_par2_entries"
                " WHERE store_name = :s AND business_date = :d"
            ),
            {"s": store_name, "d": business_date},
        )
        df.to_sql("raw_par2_entries", conn, schema="bronze", if_exists="append", index=False)
    return len(df)


# ── Per-store pipeline ─────────────────────────────────────────────────────────

async def process_store(
    store: StoreConfig,
    business_date: str,
    access_token: str,
    dry_run: bool,
    engine: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "store": store.store_name,
        "orders": 0,
        "entries": 0,
        "inserted": 0,
        "error": None,
    }
    try:
        client = PARSoapClient(store.endpoint, access_token, store.location_token)
        raw = await client.get_orders(business_date)
        orders, entries = parse_orders(raw)
        result["orders"] = len(orders)
        result["entries"] = len(entries)

        raw_par2_rows = build_raw_par2_rows(orders, entries, store.store_name, business_date)

        if dry_run:
            print(f"\n[dry-run] {store.store_name}: {len(orders)} orders, {len(entries)} entries")
            print(f"[dry-run] bronze.raw_par2 rows to insert: {len(raw_par2_rows)}")
            if raw_par2_rows:
                print(f"[dry-run] First raw_par2 row:\n  {raw_par2_rows[0]}")
            if entries:
                print(f"[dry-run] First entry row:\n  {entries[0]}")
            result["inserted"] = len(raw_par2_rows)
            return result

        n_par2 = write_raw_par2(engine, raw_par2_rows, store.store_name, business_date)
        n_entries = write_entries(engine, entries, store.store_name, business_date)
        result["inserted"] = n_par2 + n_entries
        print(
            f"[{store.store_name}] {n_par2} rows → bronze.raw_par2 | "
            f"{n_entries} rows → bronze.raw_par2_entries"
        )
    except Exception as exc:
        result["error"] = str(exc)
        print(f"[{store.store_name}] ERROR: {exc}", file=sys.stderr)
    return result


# ── Main ───────────────────────────────────────────────────────────────────────

async def run(business_date: str, store_filter: str | None, dry_run: bool) -> None:
    access_token = os.getenv("PAR_ACCESS_TOKEN")
    if not access_token:
        sys.exit("ERROR: PAR_ACCESS_TOKEN not set in .env")

    all_stores = load_store_configs()
    if not all_stores:
        sys.exit("ERROR: no store configs found — set PAR_LOCATION_TOKEN_* or PAR_SANDBOX_LOCATION_TOKEN")

    if store_filter:
        stores = [s for s in all_stores if s.store_name == store_filter.upper()]
        if not stores:
            available = [s.store_name for s in all_stores]
            sys.exit(f"ERROR: store '{store_filter}' not found. Available: {available}")
    else:
        stores = all_stores

    engine = None if dry_run else create_engine(os.environ["SUPABASE_DB_URL"])

    results = []
    for store in stores:
        r = await process_store(store, business_date, access_token, dry_run, engine)
        results.append(r)

    total_orders = sum(r["orders"] for r in results)
    total_inserted = sum(r["inserted"] for r in results)
    errors = [r for r in results if r["error"]]

    print(f"\n{'='*52}")
    print(f"Date: {business_date}  |  Stores processed: {len(results)}")
    print(f"Total orders fetched : {total_orders}")
    action = "would insert" if dry_run else "inserted"
    print(f"Total records {action}: {total_inserted}")
    for r in results:
        status = (
            f"ERROR: {r['error']}"
            if r["error"]
            else f"OK  {r['orders']} orders  {r['inserted']} records"
        )
        print(f"  {r['store']:<20} {status}")

    if errors:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="PAR POS ingestion pipeline")
    parser.add_argument(
        "--date",
        default=str(date.today() - timedelta(days=1)),
        help="Business date YYYY-MM-DD (default: yesterday)",
    )
    parser.add_argument("--store", help="Run for a single store only (e.g. SANDBOX)")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing to DB")
    args = parser.parse_args()
    asyncio.run(run(args.date, args.store, args.dry_run))


if __name__ == "__main__":
    main()
