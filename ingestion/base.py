from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class FileBasedIngester(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @property
    @abstractmethod
    def target_table(self) -> str: ...

    @property
    @abstractmethod
    def date_column(self) -> str: ...

    @abstractmethod
    def list_files(self, data_dir: Path) -> list[Path]: ...

    @abstractmethod
    def extract_file(self, filepath: Path) -> pd.DataFrame: ...

    @property
    def scope_column(self) -> str | None:
        """Optional extra equality predicate for the incremental per-file DELETE.

        When a source ships ONE partition per file (e.g. LS2 = one store per file),
        the date-range-only DELETE (`WHERE Date BETWEEN min AND max`) would wipe rows
        belonging to OTHER partitions that overlap the same date range, then re-append
        only this file's rows — a cross-partition clobber. Returning a column name here
        makes the loader add `AND "<col>" = <the file's single value>`, so a file for
        store A can never delete store B's rows.

        Default None = date-range-only delete, correct for single-source tables (e.g.
        raw_par2_csv, which holds only CSV rows)."""
        return None
