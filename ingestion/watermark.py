from sqlalchemy import Engine, text


class WatermarkManager:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS ingestion"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS bronze"))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS ingestion.processed_files ("
                "    source_name  TEXT        NOT NULL,"
                "    filename     TEXT        NOT NULL,"
                "    row_count    INT,"
                "    loaded_at    TIMESTAMPTZ DEFAULT now(),"
                "    PRIMARY KEY (source_name, filename)"
                ")"
            ))
            conn.commit()

    def get_processed(self, source_name: str) -> set[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT filename FROM ingestion.processed_files "
                    "WHERE source_name = :s"
                ),
                {"s": source_name},
            ).fetchall()
        return {r[0] for r in rows}

    def mark_processed(self, conn, source_name: str, filename: str, row_count: int) -> None:
        conn.execute(
            text(
                "INSERT INTO ingestion.processed_files (source_name, filename, row_count) "
                "VALUES (:s, :f, :n) "
                "ON CONFLICT (source_name, filename) DO UPDATE "
                "SET loaded_at = now(), row_count = EXCLUDED.row_count"
            ),
            {"s": source_name, "f": filename, "n": row_count},
        )

    def clear_processed(self, conn, source_name: str) -> None:
        conn.execute(
            text("DELETE FROM ingestion.processed_files WHERE source_name = :s"),
            {"s": source_name},
        )
