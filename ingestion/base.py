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
