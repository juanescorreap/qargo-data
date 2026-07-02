import re
from pathlib import Path

import pandas as pd

from ..base import FileBasedIngester

_CURRENCY_COLS_PAR = [
    "Price", "Discount Total", "Promotion Total",
    "Taxes", "Net Sales", "Gross Sales", "Total Sales",
]


class PAR2CSVIngester(FileBasedIngester):
    @property
    def source_name(self) -> str:
        return "par2"

    @property
    def target_table(self) -> str:
        # C4 fix: CSV writes to its own physical table. The generic loader's
        # range DELETE (WHERE Date BETWEEN min AND max, all stores) is safe here
        # because raw_par2_csv holds ONLY CSV rows — it can never clobber API data.
        return "raw_par2_csv"

    @property
    def date_column(self) -> str:
        return "Date"

    def list_files(self, data_dir: Path) -> list[Path]:
        return sorted(data_dir.glob("DDBB_*.csv"))

    def extract_file(self, filepath: Path) -> pd.DataFrame:
        df = pd.read_csv(filepath)
        if df.empty:
            return df

        df = df.rename(columns={"Closed Date/Time": "Date"})
        df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y %I:%M %p").dt.date

        for col in _CURRENCY_COLS_PAR:
            if col in df.columns:
                df[col] = (
                    df[col].astype(str)
                    .str.replace(r"[$,]", "", regex=True)
                    .pipe(pd.to_numeric, errors="coerce")
                )

        df["_source_file"] = filepath.name
        df["_source_system"] = self.source_name
        df["_ingested_at"] = pd.Timestamp.now(tz="UTC")  # tz-aware UTC (C5 load watermark)
        return df


def _store_name_from_ls_filename(filename: str) -> str:
    """
    qargocoffee-hqaccount_qargocoffeeberkeley_transactions_... → Qargo Coffee Berkeley
    """
    match = re.search(r"hqaccount_qargocoffee(\w+)_transactions", filename)
    if not match:
        return "Unknown"
    raw = match.group(1)
    # Capitalize each word after splitting on common delimiters already in the name
    return "Qargo Coffee " + raw.replace("-", " ").title()


class LS2CSVIngester(FileBasedIngester):
    @property
    def source_name(self) -> str:
        return "ls2"

    @property
    def target_table(self) -> str:
        return "raw_ls2"

    @property
    def date_column(self) -> str:
        return "Date"

    def list_files(self, data_dir: Path) -> list[Path]:
        return sorted(data_dir.glob("qargocoffee-hqaccount_*_transactions_*.csv"))

    def extract_file(self, filepath: Path) -> pd.DataFrame:
        df = pd.read_csv(filepath, sep=";", encoding="latin-1")
        if df.empty:
            return df

        # TRANSITORY_COMP and TRANSITORY_OPEN are internal Lightspeed state records,
        # not sales. VOID rows are also excluded. Only SALE and UPDATE are meaningful.
        df = df[df["Type"].isin(["SALE", "UPDATE"])].copy()

        df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%y %I:%M %p").dt.date
        df["Location"] = _store_name_from_ls_filename(filepath.name)

        df["_source_file"] = filepath.name
        df["_source_system"] = self.source_name
        df["_ingested_at"] = pd.Timestamp.now(tz="UTC")  # tz-aware UTC (C5 load watermark)
        return df
