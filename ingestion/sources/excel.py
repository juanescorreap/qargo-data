from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..base import BaseIngester

_EXCEL_PATH = Path(__file__).parents[2] / "data" / "General_Sales_Control.xlsx"


class PAR2Ingester(BaseIngester):
    @property
    def source_name(self) -> str:
        return "par2"

    @property
    def target_table(self) -> str:
        return "raw_par2"

    @property
    def date_column(self) -> str:
        return "Date"

    def extract(self, since: date) -> pd.DataFrame:
        df = pd.read_excel(_EXCEL_PATH, sheet_name="DDBB PAR2", header=0)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df = df[df["Date"] > since].copy()
        df["_ingested_at"] = datetime.utcnow()
        df["_source_system"] = self.source_name
        df["_source_file"] = _EXCEL_PATH.name
        return df


class LS2Ingester(BaseIngester):
    @property
    def source_name(self) -> str:
        return "ls2"

    @property
    def target_table(self) -> str:
        return "raw_ls2"

    @property
    def date_column(self) -> str:
        return "Date"

    def extract(self, since: date) -> pd.DataFrame:
        df = pd.read_excel(_EXCEL_PATH, sheet_name="DDBB LS2", header=0)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df = df[df["Date"] > since].copy()
        df["_ingested_at"] = datetime.utcnow()
        df["_source_system"] = self.source_name
        df["_source_file"] = _EXCEL_PATH.name
        return df
