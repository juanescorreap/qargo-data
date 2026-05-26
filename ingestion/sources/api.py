from datetime import date

import pandas as pd

from ..base import BaseIngester


class APIIngester(BaseIngester):
    """Stub para ingesta vía endpoint de API REST.

    Cuando el endpoint esté disponible, implementar extract() realizando
    la llamada HTTP filtrando registros con fecha > since y retornando
    un DataFrame con las mismas columnas que el ingester equivalente de Excel.
    """

    def __init__(self, source_name: str, target_table: str, date_column: str, base_url: str):
        self._source_name = source_name
        self._target_table = target_table
        self._date_column = date_column
        self.base_url = base_url

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def target_table(self) -> str:
        return self._target_table

    @property
    def date_column(self) -> str:
        return self._date_column

    def extract(self, since: date) -> pd.DataFrame:
        raise NotImplementedError(
            f"APIIngester '{self.source_name}' no implementado. "
            f"Implementar llamada a {self.base_url} filtrando desde {since}."
        )
