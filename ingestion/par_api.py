"""
PAR POS (Brink) Sales2.svc — cliente SOAP con zeep.

WSDL oficial: https://cdn.parpos.com/WSDL/latest/Sales2.xml
Namespace:    http://www.brinksoftware.com/webservices/sales/v2

Uso:
    python ingestion/par_api.py                  # fecha de hoy
    python ingestion/par_api.py --date 2026-05-01
    python ingestion/par_api.py --get-business-date  # fecha actual del POS

Requiere en .env:
    PAR_ACCESS_TOKEN=J0flLsIYVU2PH+Qg/kxuoQ==
    PAR_SANDBOX_LOCATION_UID=6d8f85f7-ec3f-4372-b7ac-f19fdedfcae5
    PAR_ENDPOINT=https://admin-apiint.brinkpos.net/Sales2.svc   # opcional
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from requests import Session
from zeep import Client, Settings
from zeep.transports import Transport

load_dotenv(Path(__file__).parents[1] / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WSDL_URL   = "https://cdn.parpos.com/WSDL/latest/Sales2.xml"
ENDPOINT   = os.getenv("PAR_ENDPOINT", "https://admin-apiint.brinkpos.net/Sales2.svc")
ACCESS_TOKEN = os.environ["PAR_ACCESS_TOKEN"]
LOCATION_UID = os.environ["PAR_SANDBOX_LOCATION_UID"]

# ---------------------------------------------------------------------------
# zeep client — built once, tokens injected as HTTP headers
# ---------------------------------------------------------------------------


def _build_client() -> Client:
    session = Session()
    session.headers.update({
        "AccessToken":   ACCESS_TOKEN,
        "LocationToken": LOCATION_UID,
    })
    transport = Transport(session=session, timeout=30)
    settings  = Settings(strict=False, xml_huge_tree=True)
    client    = Client(wsdl=WSDL_URL, transport=transport, settings=settings)
    # Point at the sandbox (or production) endpoint instead of the WSDL default
    client.service._binding_options["address"] = ENDPOINT
    return client


# ---------------------------------------------------------------------------
# GetCurrentBusinessDate
# ---------------------------------------------------------------------------


def get_business_date(client: Client) -> None:
    print(f"→ GetCurrentBusinessDate  location={LOCATION_UID}")
    reply = client.service.GetCurrentBusinessDate()
    print(f"  ResultCode : {reply.ResultCode}")
    print(f"  Message    : {reply.Message}")
    if hasattr(reply, "BusinessDate") and reply.BusinessDate:
        print(f"  BusinessDate: {reply.BusinessDate}")


# ---------------------------------------------------------------------------
# GetOrders
# ---------------------------------------------------------------------------


def get_orders(client: Client, business_date: date) -> None:
    # GetOrders expects a dateTime — send midnight UTC of the requested date
    biz_dt = datetime(
        business_date.year, business_date.month, business_date.day,
        tzinfo=timezone.utc,
    )

    print(f"→ GetOrders  location={LOCATION_UID}  businessDate={business_date}")
    print(f"  endpoint  : {ENDPOINT}")
    print()

    GetOrdersRequest = client.get_type(
        "{http://www.brinksoftware.com/webservices/sales/v2}GetOrdersRequest"
    )
    request_obj = GetOrdersRequest(
        BusinessDate=biz_dt,
        ExcludeOpenOrders=False,
    )

    reply = client.service.GetOrders(request=request_obj)

    print(f"ResultCode : {reply.ResultCode}")
    print(f"Message    : {reply.Message}")

    if reply.ResultCode != 0:
        print(f"\n[!] Non-zero ResultCode — call failed.")
        return

    orders = reply.Orders.Order if (reply.Orders and reply.Orders.Order) else []

    if not orders:
        print("\nNo orders found — sandbox may need test transactions.")
        print(
            "\nTo create test data in the sandbox:\n"
            "  1. Log in at https://admin-apiint.parpos.com\n"
            "  2. Open a register session and clock in as cashier 1234\n"
            "  3. Ring items and close an order\n"
            "  4. Re-run:  python ingestion/par_api.py --date <today>"
        )
        return

    print(f"\nOrders found: {len(orders)}")
    print("─" * 50)
    first = orders[0]
    print("First order:")
    print(f"  Id            : {first.Id}")
    print(f"  Number        : {first.Number}")
    print(f"  BusinessDate  : {first.BusinessDate}")
    print(f"  OpenedTime    : {first.OpenedTime}")
    print(f"  ClosedTime    : {first.ClosedTime}")
    print(f"  IsClosed      : {first.IsClosed}")
    print(f"  NetSales      : {first.NetSales}")
    print(f"  GrossSales    : {first.GrossSales}")
    print(f"  Total         : {first.Total}")
    print(f"  Tax           : {first.Tax}")
    print(f"  TerminalId    : {first.TerminalId}")
    print(f"  EmployeeId    : {first.EmployeeId}")
    entries = first.Entries.OrderEntry if (first.Entries and first.Entries.OrderEntry) else []
    print(f"  Entries       : {len(entries)} item(s)")
    for entry in entries[:5]:
        print(f"    • {entry.Name}  qty={entry.Quantity}  price={entry.Price}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="PAR POS Sales2 SOAP client")
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Business date to query (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--get-business-date",
        action="store_true",
        help="Call GetCurrentBusinessDate instead of GetOrders",
    )
    args = parser.parse_args()

    print(f"Building zeep client from WSDL …")
    client = _build_client()
    print(f"Client ready.\n")

    if args.get_business_date:
        get_business_date(client)
    else:
        try:
            business_date = date.fromisoformat(args.date)
        except ValueError:
            sys.exit(f"Invalid date: {args.date}  (expected YYYY-MM-DD)")
        get_orders(client, business_date)


if __name__ == "__main__":
    main()
