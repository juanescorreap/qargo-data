from pathlib import Path

from sqlalchemy import Engine, text

from .base import FileBasedIngester
from .watermark import WatermarkManager


class FileBasedLoader:
    def __init__(self, engine: Engine, data_dir: Path):
        self.engine = engine
        self.data_dir = data_dir
        self.watermarks = WatermarkManager(engine)

    def load(self, ingester: FileBasedIngester, full_refresh: bool = False) -> int:
        all_files = ingester.list_files(self.data_dir)

        if not all_files:
            print(f"[{ingester.source_name}] No se encontraron archivos en {self.data_dir}.")
            return 0

        if full_refresh:
            files_to_process = all_files
            with self.engine.connect() as conn:
                conn.execute(
                    text(f'DROP TABLE IF EXISTS bronze."{ingester.target_table}" CASCADE')
                )
                self.watermarks.clear_processed(conn, ingester.source_name)
                conn.commit()
        else:
            processed = self.watermarks.get_processed(ingester.source_name)
            files_to_process = [f for f in all_files if f.name not in processed]

        if not files_to_process:
            print(f"[{ingester.source_name}] Sin archivos nuevos (todos ya procesados).")
            return 0

        print(f"[{ingester.source_name}] {len(files_to_process)} archivo(s) por procesar.")
        total = 0

        for filepath in files_to_process:
            print(f"[{ingester.source_name}] Leyendo {filepath.name}...")
            df = ingester.extract_file(filepath)

            if df.empty:
                print(f"[{ingester.source_name}] {filepath.name}: sin datos, omitido.")
                continue

            min_date = df[ingester.date_column].min()
            max_date = df[ingester.date_column].max()
            print(f"[{ingester.source_name}] {len(df)} filas ({min_date} → {max_date})")

            with self.engine.connect() as conn:
                table_exists = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'bronze' AND table_name = :t)"
                    ),
                    {"t": ingester.target_table},
                ).scalar()

                if table_exists:
                    conn.execute(
                        text(
                            f'DELETE FROM bronze."{ingester.target_table}" '
                            f'WHERE "{ingester.date_column}" BETWEEN :min_d AND :max_d'
                        ),
                        {"min_d": min_date, "max_d": max_date},
                    )
                conn.commit()

            if_exists = "append" if table_exists else "replace"
            df.to_sql(
                ingester.target_table,
                self.engine,
                schema="bronze",
                if_exists=if_exists,
                index=False,
            )

            with self.engine.connect() as conn:
                conn.execute(
                    text(
                        f'CREATE INDEX IF NOT EXISTS idx_{ingester.target_table}_date '
                        f'ON bronze."{ingester.target_table}" ("{ingester.date_column}")'
                    )
                )
                self.watermarks.mark_processed(conn, ingester.source_name, filepath.name, len(df))
                conn.commit()

            print(f"[{ingester.source_name}] ✓ {filepath.name} cargado ({len(df)} filas).")
            total += len(df)

        print(f"[{ingester.source_name}] Total: {total} filas cargadas.")
        return total
